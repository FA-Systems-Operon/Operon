"""Strip emails and phone numbers from everything sent to a model (M14).

Each value is swapped for a numbered token such as [EMAIL_1] or [PHONE_2]
before the call, and swapped back in the reply afterwards. The model never
sees the real value, but fields like phone_number and email still end up with
it, and quotes still match the source text exactly.
"""

import json
import re

from src.ai.provider import ModelProvider, ModelResponse

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"
)

# A phone needs a separator, brackets or a leading "+". A plain run of digits
# such as a 10-digit NEQ is left alone: business_number must stay a business
# number, not turn into [PHONE_1] (see commit feec516).
#
# The start must not follow a word character, except when that character is
# the letter of an escape like a literal backslash-n: text that was
# JSON-encoded before it reaches us holds "\\n514-555-1234", and the "n" there
# is not part of the number.
#
# Where a number may break over two lines: a real line break, or one escaped
# by JSON-encoding (a backslash-n, possibly with extra backslashes when the
# text was encoded more than once).
_LINE_BREAK = r"(?:\r\n|\s|\\+r\\+n|\\+[nrt])"

PHONE_PATTERN = re.compile(
    r"(?:(?<=\\[nrt])|(?<![\w+]))(?:"
    # International: +44 20 7946 0958, +33 1 23 45 67 89, +15145551234
    r"\+\d{1,3}(?:[ .-]?\(?\d{1,4}\)?){2,5}"
    r"|"
    # North American: (514) 555-1234, 514-555-1234, 1-800-555-1234, 514.555.1234
    r"(?:1[ .-])?(?:\(\d{3}\)" + _LINE_BREAK + r"?|\d{3}[ .-])\d{3}[ .-]\d{4}"
    r")(?:" + _LINE_BREAK + r"?(?:x|ext\.?)\s?\d{1,5})?(?!\w)"
)

_TOKEN_PATTERN = re.compile(r"\[(?:EMAIL|PHONE)_\d+\]")


def redact(
    text: str, tokens: dict[str, str] | None = None
) -> tuple[str, dict[str, str]]:
    """Replace emails and phones with tokens. Returns (text, token -> original).

    Pass the same `tokens` dict for several texts in one call so a value that
    appears in both gets the same token.
    """
    tokens = {} if tokens is None else tokens
    by_value = {value: token for token, value in tokens.items()}

    def substitute(kind: str):
        def replace(match: re.Match) -> str:
            value = match.group(0)
            if value not in by_value:
                count = sum(1 for token in tokens if token.startswith(f"[{kind}_"))
                token = f"[{kind}_{count + 1}]"
                tokens[token] = value
                by_value[value] = token
            return by_value[value]

        return replace

    # Emails first, so digits inside an address are never read as a phone.
    text = EMAIL_PATTERN.sub(substitute("EMAIL"), text)
    text = PHONE_PATTERN.sub(substitute("PHONE"), text)
    return text, tokens


def restore(text: str, tokens: dict[str, str], *, json_escape: bool = False) -> str:
    """Put the original values back wherever the model repeated a token.

    With `json_escape`, each value goes back escaped as it would be inside a
    JSON string. A phone split over two lines then comes back as "\\n" instead
    of a raw line break, so the reply stays valid JSON, and the parsed value
    is still exactly the original.

    A value taken from JSON-encoded text (it holds a backslash, which a phone
    or email otherwise never does) is already escaped, so it goes back as-is.
    """
    if not tokens:
        return text

    def replace(match: re.Match) -> str:
        token = match.group(0)
        if token not in tokens:
            return token
        value = tokens[token]
        if json_escape and "\\" not in value:
            return json.dumps(value)[1:-1]
        return value

    return _TOKEN_PATTERN.sub(replace, text)


class RedactingProvider:
    """Wraps any ModelProvider so no email or phone number reaches it."""

    def __init__(self, inner: ModelProvider):
        self.inner = inner

    def __getattr__(self, name):
        # name, model, list_models() etc. come from the wrapped provider.
        return getattr(self.inner, name)

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_output: bool = False,
        output_schema: dict | None = None,
    ) -> ModelResponse:
        prompt, tokens = redact(prompt)
        if system is not None:
            system, tokens = redact(system, tokens)
        response = self.inner.generate(
            prompt, system=system, json_output=json_output, output_schema=output_schema
        )
        return ModelResponse(
            text=restore(
                response.text,
                tokens,
                json_escape=json_output or output_schema is not None,
            ),
            provider=response.provider,
            model=response.model,
            duration_ms=response.duration_ms,
        )
