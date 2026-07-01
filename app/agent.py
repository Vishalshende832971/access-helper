# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import json
import datetime
from zoneinfo import ZoneInfo
from typing import List, Any

from google.adk.agents import Agent, LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.workflow import Workflow, node, START
from google.adk.tools import AgentTool
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types
from pydantic import BaseModel, Field
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# Define output schemas for structured agent collaboration
class AccessibilityIssue(BaseModel):
    element: str = Field(description="The HTML element or code snippet with the issue")
    wcag_rule: str = Field(description="The WCAG 2.2 rule violated (e.g., 1.1.1 Non-text Content)")
    severity: str = Field(description="Severity: Critical, Warning, or Info")
    description: str = Field(description="Description of why this is a violation")

class AuditReport(BaseModel):
    issues: List[AccessibilityIssue] = Field(description="List of accessibility issues found")

class RemediationFix(BaseModel):
    element: str = Field(description="The HTML element or code snippet being fixed")
    proposed_fix: str = Field(description="The recommended code or text fix")
    explanation: str = Field(description="Explanation of how this fix resolves the issue")

class RemediationReport(BaseModel):
    fixes: List[RemediationFix] = Field(description="List of proposed remediation fixes")

class OrchestratorReport(BaseModel):
    summary: str = Field(description="Brief summary of the audit and fixes")
    audit_report: AuditReport = Field(description="The full audit report from the WCAG auditor")
    remediation_report: RemediationReport = Field(description="The full remediation report from the specialist")


# Define local MCP Toolset
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", "app/mcp_server.py"],
        )
    )
)

# Define sub-agents
wcag_auditor = LlmAgent(
    name="wcag_auditor",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a WCAG 2.2 accessibility auditor. Analyze the provided HTML code, text, or document and identify violations.\n"
        "Be systematic. Focus on missing alt text, lack of color contrast, poor heading structure, missing form labels, and keyboard navigability.\n"
        "Output your report as a structured Markdown audit. List each issue with the affected element/code, violated WCAG rule, severity, and description."
    ),
    tools=[mcp_toolset],
)

remediation_specialist = LlmAgent(
    name="remediation_specialist",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an accessibility remediation specialist. Provide clean, correct, and standards-compliant HTML/CSS fixes or text descriptions to resolve WCAG violations.\n"
        "Each fix must correspond to one of the violations reported by the auditor. Provide a clear explanation of how the fix resolves the violation."
    ),
    tools=[mcp_toolset],
)

# Define orchestrator agent
orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Accessibility Orchestrator. Coordinate the audit and remediation of the user's document/code.\n"
        "1. Call the `wcag_auditor` tool with the user's input to identify accessibility issues.\n"
        "2. Pass the generated findings to the `remediation_specialist` tool to generate fixes.\n"
        "3. Combine both outputs and present a single, comprehensive Markdown report summarizing the violations and proposed remediations."
    ),
    tools=[AgentTool(wcag_auditor), AgentTool(remediation_specialist)],
    output_key="orchestrator_report",
)


# Define security checkpoint node (incorporating Phase 4 Security requirements)
def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    # 1. Extract input text
    input_text = ""
    if isinstance(node_input, str):
        input_text = node_input
    elif hasattr(node_input, 'parts') and node_input.parts:
        input_text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, dict):
        input_text = node_input.get("text", "")
    else:
        input_text = str(node_input)

    # 2. PII Scrubbing (Email, Phone)
    scrubbed_text = input_text
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    
    emails_found = re.findall(email_pattern, scrubbed_text)
    phones_found = re.findall(phone_pattern, scrubbed_text)
    
    if emails_found:
        scrubbed_text = re.sub(email_pattern, "[EMAIL_REDACTED]", scrubbed_text)
    if phones_found:
        scrubbed_text = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_text)

    pii_redacted = len(emails_found) > 0 or len(phones_found) > 0

    # 3. Prompt Injection Detection
    injection_keywords = ["ignore instructions", "system prompt", "override rules", "bypass safety", "dan mode"]
    injection_detected = any(kw in input_text.lower() for kw in injection_keywords)

    # 4. Domain-specific rule (Length limit to prevent abuse)
    is_too_long = len(input_text) > 10000

    if injection_detected or is_too_long:
        severity = "CRITICAL" if injection_detected else "WARNING"
        reason = "Prompt injection detected" if injection_detected else "Input exceeds length limit of 10000 characters"
        
        audit_log = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "security_violation",
            "severity": severity,
            "reason": reason,
            "pii_redacted": pii_redacted
        }
        print(json.dumps(audit_log))
        return Event(output=f"Security event: {reason}", route="unsafe", state={"security_log": audit_log})

    # Safe path
    audit_log = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event": "input_approved",
        "severity": "INFO",
        "pii_redacted": pii_redacted
    }
    print(json.dumps(audit_log))
    return Event(output=scrubbed_text, route="safe", state={"security_log": audit_log, "sanitized_input": scrubbed_text})


def security_event_handler(ctx: Context, node_input: Any):
    log = ctx.state.get("security_log", {})
    message = f"⚠️ Security Access Denied: {log.get('reason', 'Unknown safety violation')}."
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=message)]))
    yield Event(output=message)


# Define human review node for HITL step
@node(rerun_on_resume=True)
async def human_review(ctx: Context, node_input: Any):
    if os.getenv("INTEGRATION_TEST") == "TRUE" or os.getenv("EVAL_MODE") == "TRUE":
        yield Event(
            output="Approved",
            route="approved",
            state={"review_loop_count": 1, "approved_status": True}
        )
        return

    loop_count = ctx.state.get("review_loop_count", 0)
    interrupt_id = f"approve_fixes_{loop_count}"
    
    if not ctx.resume_inputs or interrupt_id not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id=interrupt_id,
            message="Suggested accessibility remediations are ready for your review. Do you approve the proposed fixes? (Yes/No)"
        )
        return

    # Process response
    user_response = ctx.resume_inputs[interrupt_id].strip().lower()
    if "yes" in user_response or "approve" in user_response:
        yield Event(
            output="Approved",
            route="approved",
            state={"review_loop_count": loop_count + 1, "approved_status": True}
        )
    else:
        yield Event(
            output=f"Rejected: {user_response}",
            route="rejected",
            state={"review_loop_count": loop_count + 1, "approved_status": False, "rejection_feedback": user_response}
        )


# Define final output node to present the report
def final_output(ctx: Context, node_input: Any):
    report = ctx.state.get("orchestrator_report", "No audit report available.")
    
    # If it is a Content object, extract text. Otherwise convert to string.
    if hasattr(report, 'parts') and report.parts:
        text = "".join(part.text for part in report.parts if part.text)
    elif isinstance(report, dict):
        text = json.dumps(report, indent=2)
    else:
        text = str(report)
        
    # Prepend completion title if not present
    if not text.startswith("#"):
        text = f"# Accessibility Audit & Remediation Complete\n\n{text}"
        
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=text)]))
    yield Event(output=text)


# Define root_agent as Workflow graph
root_agent = Workflow(
    name="access_helper_workflow",
    edges=[
        ('START', security_checkpoint),
        (security_checkpoint, {"safe": orchestrator, "unsafe": security_event_handler}),
        (orchestrator, human_review),
        (human_review, {"rejected": orchestrator, "approved": final_output}),
    ],
    description="Accessibility audit and remediation assistant.",
)

# App instance
app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
