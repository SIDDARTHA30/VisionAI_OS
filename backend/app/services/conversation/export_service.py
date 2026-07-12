import json
import uuid
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository


class ExportService:
    """Service layer responsible for formatting and serializing conversation histories for user download."""

    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.msg_repo = MessageRepository()

    async def get_export_data(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int,
        export_format: str
    ) -> tuple[bytes, str, str]:
        """
        Fetch conversation history and format into target serialization.
        Returns: (file_bytes, media_type, filename)
        """
        conv = await self.conv_repo.get_by_id(db, conversation_id, user_id)
        if not conv:
            raise ValueError("Conversation not found or unauthorized access.")

        # Get active messages
        all_messages = await self.msg_repo.list_by_conversation(db, conversation_id)
        active_messages = [m for m in all_messages if m.is_active and m.status == "COMPLETED"]

        formatted_messages = [
            {"role": m.role, "content": m.content, "created_at": str(m.created_at)}
            for m in active_messages
        ]

        title_slug = conv.title.lower().replace(" ", "_")[:30]
        fmt = export_format.lower()

        if fmt == "json":
            content = json.dumps(
                {
                    "title": conv.title,
                    "summary": conv.summary,
                    "messages": formatted_messages
                },
                indent=2
            )
            return content.encode("utf-8"), "application/json", f"{title_slug}.json"

        elif fmt == "markdown" or fmt == "md":
            lines = [f"# {conv.title}", f"*{conv.summary or 'No summary available.'}*", ""]
            for m in formatted_messages:
                role_label = "User" if m["role"] == "user" else "Assistant"
                lines.append(f"### {role_label}")
                lines.append(m["content"])
                lines.append("")
            content = "\n".join(lines)
            return content.encode("utf-8"), "text/markdown", f"{title_slug}.md"

        elif fmt == "html":
            lines = [
                "<!DOCTYPE html>",
                "<html>",
                "<head>",
                f"<title>{conv.title}</title>",
                "<style>",
                "body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; }",
                ".chat-bubble { padding: 15px; margin: 10px 0; border-radius: 8px; }",
                ".user { background-color: #f0f0f0; }",
                ".assistant { background-color: #e0f7fa; border-left: 5px solid #00acc1; }",
                "h1 { color: #333; }",
                "</style>",
                "</head>",
                "<body>",
                f"<h1>{conv.title}</h1>",
                f"<p><i>{conv.summary or ''}</i></p>",
                "<hr/>"
            ]
            for m in formatted_messages:
                cls = "user" if m["role"] == "user" else "assistant"
                label = "User" if m["role"] == "user" else "Assistant"
                lines.append(f"<div class='chat-bubble {cls}'>")
                lines.append(f"<strong>{label}</strong><br/>")
                lines.append(m["content"].replace("\n", "<br/>"))
                lines.append("</div>")
            lines.append("</body></html>")
            content = "\n".join(lines)
            return content.encode("utf-8"), "text/html", f"{title_slug}.html"

        elif fmt == "docx":
            # Native XML/HTML format that Microsoft Word opens natively out of the box as a document
            lines = [
                "<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>",
                "<head><title>Export</title></head>",
                "<body>",
                f"<h1>{conv.title}</h1>",
                f"<p><i>{conv.summary or ''}</i></p>",
                "<br/>"
            ]
            for m in formatted_messages:
                label = "User" if m["role"] == "user" else "Assistant"
                lines.append(f"<p><b>{label}:</b></p>")
                lines.append(f"<p>{m['content']}</p>")
                lines.append("<p>--------------------------------------------------</p>")
            lines.append("</body></html>")
            content = "\n".join(lines)
            return content.encode("utf-8"), "application/msword", f"{title_slug}.docx"

        elif fmt == "pdf":
            # Structured dependency-free PDF stream generator
            text_lines = [f"Conversation: {conv.title}", f"Summary: {conv.summary or ''}", ""]
            for m in formatted_messages:
                role = m["role"].upper()
                text_lines.append(f"--- {role} ---")
                content = m["content"]
                for chunk in content.split("\n"):
                    words = chunk.split(" ")
                    current_line = []
                    for w in words:
                        if len(" ".join(current_line + [w])) > 80:
                            text_lines.append("  " + " ".join(current_line))
                            current_line = [w]
                        else:
                            current_line.append(w)
                    if current_line:
                        text_lines.append("  " + " ".join(current_line))
                text_lines.append("")

            # PDF stream layout drawing
            stream_content = "BT\n/F1 12 Tf\n14 Lh\n50 780 Td\n"
            current_y = 780
            for line in text_lines:
                escaped = line.replace("(", "\\(").replace(")", "\\)")
                stream_content += f"({escaped}) Tj T*\n"
                current_y -= 14
                if current_y < 50:
                    stream_content += "ET"
                    break
            else:
                stream_content += "ET"

            stream_len = len(stream_content)
            pdf = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length {stream_len} >>
stream
{stream_content}
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000325 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
{325 + stream_len + 50}
%%EOF
"""
            return pdf.encode("utf-8", errors="ignore"), "application/pdf", f"{title_slug}.pdf"

        else:
            # Default to text format (TXT)
            lines = [f"Title: {conv.title}", f"Summary: {conv.summary or ''}", ""]
            for m in formatted_messages:
                role_label = "User" if m["role"] == "user" else "Assistant"
                lines.append(f"{role_label}: {m['content']}")
                lines.append("-" * 40)
            content = "\n".join(lines)
            return content.encode("utf-8"), "text/plain", f"{title_slug}.txt"
