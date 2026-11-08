import pytest

from thanzi_screen.llm import strip_reasoning


@pytest.mark.parametrize("raw,clean", [
    ("<think>plan it</think>Answer.", "Answer."),
    ("<think>a\nb\nc</think>\n\nAnswer.", "Answer."),
    ("<THINK>x</THINK>Answer", "Answer"),
    ("plan it</think>Answer.", "Answer."),                       # opening tag lost to the template
    ("Partial answer <think>still thinking when the tokens ran out", "Partial answer"),
    ("<think>one</think>A<think>two</think>B", "AB"),
    ("No tags here.", "No tags here."),
    ("  padded  ", "padded"),
    ("<think>only thoughts", ""),
])
def test_strip_reasoning(raw, clean):
    assert strip_reasoning(raw) == clean
