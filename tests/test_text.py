"""Tests for scry.text — plain-text helpers."""

from scry.text import plain_text, summarize


class TestPlainText:
    def test_strips_tags_and_entities(self) -> None:
        assert (
            plain_text("<p>Read &amp; write<br/>\n <b>barcodes</b></p>") == "Read & write barcodes"
        )

    def test_plain_input_unchanged(self) -> None:
        assert plain_text("already plain") == "already plain"

    def test_inline_tag_before_punctuation_leaves_no_space(self) -> None:
        assert plain_text("<p>Status can be <b>UNLISTED</b>.</p>") == "Status can be UNLISTED."


class TestSummarize:
    def test_short_text_unchanged(self) -> None:
        assert summarize("Short.", limit=20) == "Short."

    def test_cuts_at_sentence_end_past_midpoint(self) -> None:
        text = "First sentence here. Second sentence is longer than the limit allows."
        assert summarize(text, limit=40) == "First sentence here."

    def test_hard_cut_with_ellipsis_when_no_sentence_end(self) -> None:
        text = "x" * 50
        assert summarize(text, limit=20) == "x" * 20 + "..."

    def test_early_sentence_end_is_ignored(self) -> None:
        text = "Hi. " + "y" * 60
        assert summarize(text, limit=30) == ("Hi. " + "y" * 26) + "..."
