"""Natural language processing for free-text clinical notes (D135). Advisory only, never changes a classification (D9).

Transparent lexicon-and-scope methods, standard library only, English, offline. Not a trained model: there is no
real, authorised note data to train or validate one (I48). Independent of the screening code in both directions (D142).
"""
from .crosscheck import NoteCheck, check_note
from .extract import Extraction, Mention, extract_mentions
from .lexicon import Lexicon, LexiconError, load_lexicon
from .privacy import Redaction, Span, contains_identifiers, find_identifiers, redact

__all__ = ["NoteCheck", "check_note", "Extraction", "Mention", "extract_mentions", "Lexicon", "LexiconError",
           "load_lexicon", "Redaction", "Span", "contains_identifiers", "find_identifiers", "redact"]
