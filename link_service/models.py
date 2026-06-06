from dataclasses import dataclass, field
from datetime import datetime

# Value Object — kein id, durch Werte definiert
@dataclass(frozen=True)   # frozen=True macht es immutable
class Tag:
    name: str

    def __eq__(self, other):
        return isinstance(other, Tag) and self.name == other.name

# Aggregate Root
@dataclass
class Link:
    id: int
    url: str
    title: str
    user_id: int                        # Nur die ID — kein User-Objekt!
    tags: list[Tag] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Zugriff auf Tags NUR über den Aggregate Root
    def add_tag(self, tag: Tag):
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: Tag):
        self.tags = [t for t in self.tags if t != tag]