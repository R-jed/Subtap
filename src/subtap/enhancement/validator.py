"""Enhancement validator: ensures LLM output respects timing constraints."""

from __future__ import annotations

from dataclasses import dataclass, field

from subtap.schemas.enhancement import CleanSegment


@dataclass
class ValidationResult:
    """Result of enhancement validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class EnhancementValidator:
    """Validates enhancement output respects hard rules.

    Hard rules:
    - start_sec / end_sec must NOT change
    - Empty text is forbidden
    - Translation must preserve mapping
    """

    def validate(
        self,
        original: list[CleanSegment],
        enhanced: list[CleanSegment],
    ) -> ValidationResult:
        """Validate enhanced segments against originals.

        Args:
            original: Original segments before enhancement.
            enhanced: Enhanced segments after LLM/local processing.

        Returns:
            ValidationResult with errors if rules violated.
        """
        errors = []
        warnings = []

        if len(original) != len(enhanced):
            errors.append(
                f"Segment count mismatch: {len(original)} vs {len(enhanced)}"
            )
            return ValidationResult(valid=False, errors=errors)

        for orig, enh in zip(original, enhanced):
            # Check timing unchanged
            if abs(orig.start_sec - enh.start_sec) > 0.001:
                errors.append(
                    f"Segment {orig.segment_id}: start_sec changed "
                    f"({orig.start_sec} → {enh.start_sec})"
                )
            if abs(orig.end_sec - enh.end_sec) > 0.001:
                errors.append(
                    f"Segment {orig.segment_id}: end_sec changed "
                    f"({orig.end_sec} → {enh.end_sec})"
                )

            # Check text not empty
            if not enh.text.strip():
                errors.append(f"Segment {orig.segment_id}: text is empty")

            # Check segment_id preserved
            if orig.segment_id != enh.segment_id:
                warnings.append(
                    f"Segment ID changed: {orig.segment_id} → {enh.segment_id}"
                )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_single(
        self,
        original: CleanSegment,
        enhanced: CleanSegment,
    ) -> ValidationResult:
        """Validate a single enhanced segment.

        Args:
            original: Original segment.
            enhanced: Enhanced segment.

        Returns:
            ValidationResult.
        """
        return self.validate([original], [enhanced])
