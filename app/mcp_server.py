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

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Accessibility Services")

@mcp.tool()
def search_wcag_guidelines(topic: str) -> str:
    """Search WCAG 2.2 guidelines for a specific topic (e.g., contrast, alt text, headings, keyboard).

    Args:
        topic: The topic or concept to search for in the guidelines.
    """
    db = {
        "contrast": "WCAG 2.2 Rule 1.4.3 (Contrast Minimum): The visual presentation of text and images of text has a contrast ratio of at least 4.5:1. For large text, at least 3:1.",
        "alt text": "WCAG 2.2 Rule 1.1.1 (Non-text Content): All non-text content that is presented to the user has a text alternative that serves the equivalent purpose.",
        "headings": "WCAG 2.2 Rule 1.3.1 (Info and Relationships) & 2.4.10 (Section Headings): Heading elements (h1-h6) must be used in sequential order and convey document structure.",
        "keyboard": "WCAG 2.2 Rule 2.1.1 (Keyboard): All functionality of the content is operable through a keyboard interface without requiring specific timings for individual keystrokes.",
        "labels": "WCAG 2.2 Rule 4.1.2 (Name, Role, Value): For all user interface components (including form elements, links), the name and role can be programmatically determined.",
        "focus visible": "WCAG 2.2 Rule 2.4.7 (Focus Visible): Any keyboard operable user interface has a mode of operation where the keyboard focus indicator is visible.",
        "language": "WCAG 2.2 Rule 3.1.1 (Language of Page): The default human language of each Web page can be programmatically determined.",
        "resize": "WCAG 2.2 Rule 1.4.4 (Resize Text): Except for captions and images of text, text can be resized without assistive technology up to 200 percent without loss of content or functionality."
    }
    
    topic_lower = topic.lower()
    results = []
    for key, value in db.items():
        if key in topic_lower or topic_lower in key:
            results.append(value)
    
    if results:
        return "\n".join(results)
    return "No specific WCAG 2.2 guideline found for that topic. Ensure elements are semantic and programmatically accessible."

@mcp.tool()
def validate_color_contrast(foreground_hex: str, background_hex: str) -> str:
    """Calculate the contrast ratio between two hex colors and check if they pass WCAG standards.

    Args:
        foreground_hex: Hex code of the foreground/text color (e.g., '#333333').
        background_hex: Hex code of the background color (e.g., '#FFFFFF').
    """
    fg = foreground_hex.lstrip('#')
    bg = background_hex.lstrip('#')
    
    def get_luminance(hex_val):
        rgb = []
        for i in (0, 2, 4):
            val = int(hex_val[i:i+2], 16) / 255.0
            if val <= 0.03928:
                rgb.append(val / 12.92)
            else:
                rgb.append(((val + 0.055) / 1.055) ** 2.4)
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        
    try:
        l1 = get_luminance(fg)
        l2 = get_luminance(bg)
        
        if l1 > l2:
            ratio = (l1 + 0.05) / (l2 + 0.05)
        else:
            ratio = (l2 + 0.05) / (l1 + 0.05)
            
        pass_normal_aa = ratio >= 4.5
        pass_normal_aaa = ratio >= 7.0
        pass_large_aa = ratio >= 3.0
        pass_large_aaa = ratio >= 4.5
        
        return (
            f"Contrast Ratio: {ratio:.2f}:1\n"
            f"- Normal Text (AA): {'PASS' if pass_normal_aa else 'FAIL (needs >= 4.5:1)'}\n"
            f"- Normal Text (AAA): {'PASS' if pass_normal_aaa else 'FAIL (needs >= 7:1)'}\n"
            f"- Large Text (AA): {'PASS' if pass_large_aa else 'PASS (needs >= 3:1)'}\n"
            f"- Large Text (AAA): {'PASS' if pass_large_aaa else 'FAIL (needs >= 4.5:1)'}"
        )
    except Exception as e:
        return f"Error parsing hex codes: {str(e)}. Use format: RRGGBB or #RRGGBB"

@mcp.tool()
def get_remediation_template(violation_type: str) -> str:
    """Get code templates and standard examples for fixing specific accessibility violations.

    Args:
        violation_type: The type of violation (e.g., 'alt text', 'labels', 'headings', 'contrast', 'keyboard').
    """
    templates = {
        "alt text": "Fix: <img src=\"image.png\" alt=\"Descriptive text describing image contents\" />\nFor decorative images: <img src=\"image.png\" alt=\"\" />",
        "labels": "Fix: <label for=\"username\">Username</label>\n<input type=\"text\" id=\"username\" name=\"username\" />\nOr: <input type=\"text\" aria-label=\"Username\" />",
        "headings": "Fix: Ensure nesting structure goes h1 -> h2 -> h3 -> h4 -> h5 -> h6 without skipping levels. Example:\n<h1>Main Title</h1>\n<h2>Section Header</h2>\n<h3>Subsection Header</h3>",
        "contrast": "Fix: Use tool `validate_color_contrast` to find passing colors. E.g., change light gray text on white to dark gray (#333333) or black (#000000).",
        "keyboard": "Fix: Ensure interactive elements are semantic HTML: use <button> instead of <div onclick=\"...\">, or add tabindex=\"0\" and keydown listener if using custom elements.",
        "focus visible": "Fix: Do not use CSS rules like `outline: none` or `outline: 0` unless you provide a clear, high-contrast custom focus style. Example:\nbutton:focus {\n  outline: 2px solid #005fcc;\n  outline-offset: 2px;\n}",
        "language": "Fix: Add the `lang` attribute to the root `<html>` element. Example:\n<html lang=\"en\">\n...",
        "resize": "Fix: Avoid restricting viewport scaling in `<meta name=\"viewport\">` (do not use `user-scalable=no` or set `maximum-scale` below `2.0`). Ensure layout uses relative units (like `rem`, `em`, or `%`) instead of absolute pixels (`px`) where possible."
    }
    return templates.get(violation_type.lower(), "No template found. Focus on using semantic elements, aria-labels, and high contrast colors.")

if __name__ == "__main__":
    mcp.run()
