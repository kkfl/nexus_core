class DocumentChunker:
    def __init__(self, max_chars_per_chunk: int = 1500, overlap_chars: int = 200):
        self.max_chars = max_chars_per_chunk
        self.overlap = overlap_chars

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []

        # Simple overlap chunking preserving paragraphs roughly
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # If a single paragraph is larger than max_chars, we just split it by words/chars
            if len(para) > self.max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                # Naive character sliding window for large paragraphs
                start = 0
                while start < len(para):
                    end = start + self.max_chars
                    chunks.append(para[start:end].strip())
                    start += self.max_chars - self.overlap
                continue

            # If adding paragraph exceeds max, save current chunk and start new one
            if len(current_chunk) + len(para) + 2 > self.max_chars and current_chunk:
                chunks.append(current_chunk.strip())
                # Keep overlap by grabbing the last few chars of the previous chunk
                overlap_text = (
                    current_chunk[-self.overlap :]
                    if len(current_chunk) > self.overlap
                    else current_chunk
                )
                current_chunk = overlap_text + "\n\n" + para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks
