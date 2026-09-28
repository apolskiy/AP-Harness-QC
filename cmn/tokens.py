# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The token counts a bill distinguishes, and nothing that depends on anything.

**Its own module because of a cycle.** These records are needed by
``cmn.observations`` (an observation carries them), by ``cmn.pricing`` (a price
applies to them) and by every adapter (a provider reports them). Holding them in
``cmn.pricing`` put ``observations`` behind ``pricing``, which is behind
``config``, which is behind ``verdict``, which is behind ``observations``.

Nothing here imports from this project, which is what makes it safe to import
from anywhere in it.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TokenUsage:
    """What one request consumed, in the four categories a bill distinguishes.

    Attributes:
        input_tokens (int): Everything sent, including a context document and a
            rubric. **The larger half for this corpus**, which is why reading
            only the output count understated every figure.
        output_tokens (int): The visible response, as the provider counts it.
        thinking_tokens (int): Reasoning the provider billed and did not return
            in the text. **Reported separately and billed as output**, so it is
            held separately here and priced at the output rate.
        cached_input_tokens (int): Input served from the provider's cache, at a
            tenth of the input rate. **Subtracted from the input count** by the
            adapter that reports it, so the two never double-count.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_input_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Return the sum of two usages, so a run can accumulate them.

        Args:
            other (TokenUsage): The usage to add.

        Returns:
            TokenUsage: The totals.
        """
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
        )

    @property
    def billable_output(self) -> int:
        """Return the tokens billed at the output rate.

        Returns:
            int: Visible output plus thinking, because every provider in this
            table bills the second as the first.
        """
        return self.output_tokens + self.thinking_tokens


@dataclass(frozen=True)
class CaseUsage:
    """What one observation consumed, on both sides of a judged case.

    **One field on an observation rather than six.** `.pylintrc` derives its
    attribute limit from the design's field list and says a record growing past
    it should be questioned instead of the number: what a case consumed is one
    fact about an execution, and the judge's half is a part of that fact rather
    than a peer of `outcome` and `priority`.

    Attributes:
        candidate (TokenUsage): What the model under test consumed.
        judge (TokenUsage): What the judge consumed, which for this corpus is
            the larger input of the two: it carries the rubric, every criterion
            and anchor, and the candidate's response as well.
    """

    candidate: TokenUsage = field(default_factory=TokenUsage)
    judge: TokenUsage = field(default_factory=TokenUsage)

    @property
    def billable(self) -> TokenUsage:
        """Return both sides added, which is what a price applies to.

        Returns:
            TokenUsage: The sum. **Both sides are priced at the same rates**
            here because the roster judges with the candidate's own engine, and
            a run that judged elsewhere would price the two separately.
        """
        return self.candidate + self.judge
