"""Deterministic document chunker with offset tracking for citation support."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkInfo:
    """A chunk of text with its position in the original document."""

    text: str
    start_char: int
    end_char: int
    char_count: int
    token_count: int  # estimated


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


class DocumentChunker:
    def __init__(self, max_chars_per_chunk: int = 1500, overlap_chars: int = 200):
        self.max_chars = max_chars_per_chunk
        self.overlap = overlap_chars

    def chunk_text(self, text: str) -> list[str]:
        """Legacy API — returns plain text chunks."""
        return [c.text for c in self.chunk_text_with_offsets(text)]

    def chunk_text_with_offsets(self, text: str) -> list[ChunkInfo]:
        """Chunk text and return offset metadata for citation support.

        Uses paragraph-aware splitting with overlap. Deterministic for
        the same input text so re-ingest produces identical chunks.
        """
        if not text:
            return []

        paragraphs = text.split("\n\n")
        chunks: list[ChunkInfo] = []
        current_chunk = ""
        # Track position in the original text
        current_start = 0  # start of current_chunk in original text
        para_offset = 0  # running offset through original text

        for para in paragraphs:
            para_start = text.find(para, para_offset)
            if para_start == -1:
                para_start = para_offset
            para_end = para_start + len(para)

            # If a single paragraph is larger than max_chars, split it
            if len(para) > self.max_chars:
                if current_chunk:
                    chunks.append(
                        ChunkInfo(
                            text=current_chunk.strip(),
                            start_char=current_start,
                            end_char=current_start + len(current_chunk.rstrip()),
                            char_count=len(current_chunk.strip()),
                            token_count=_estimate_tokens(current_chunk.strip()),
                        )
                    )
                    current_chunk = ""

                # Sliding window for large paragraphs
                start = 0
                while start < len(para):
                    end = start + self.max_chars
                    chunk_text = para[start:end].strip()
                    if chunk_text:
                        chunks.append(
                            ChunkInfo(
                                text=chunk_text,
                                start_char=para_start + start,
                                end_char=para_start + min(end, len(para)),
                                char_count=len(chunk_text),
                                token_count=_estimate_tokens(chunk_text),
                            )
                        )
                    start += self.max_chars - self.overlap
                para_offset = para_end
                current_start = para_end
                continue

            # If adding paragraph exceeds max, save current chunk
            if len(current_chunk) + len(para) + 2 > self.max_chars and current_chunk:
                chunks.append(
                    ChunkInfo(
                        text=current_chunk.strip(),
                        start_char=current_start,
                        end_char=current_start + len(current_chunk.rstrip()),
                        char_count=len(current_chunk.strip()),
                        token_count=_estimate_tokens(current_chunk.strip()),
                    )
                )
                # Keep overlap from the end of the previous chunk
                overlap_text = (
                    current_chunk[-self.overlap :]
                    if len(current_chunk) > self.overlap
                    else current_chunk
                )
                current_start = para_start - len(overlap_text)
                current_chunk = overlap_text + "\n\n" + para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_start = para_start
                    current_chunk = para

            para_offset = para_end

        if current_chunk:
            chunks.append(
                ChunkInfo(
                    text=current_chunk.strip(),
                    start_char=current_start,
                    end_char=current_start + len(current_chunk.rstrip()),
                    char_count=len(current_chunk.strip()),
                    token_count=_estimate_tokens(current_chunk.strip()),
                )
            )

        return chunks
