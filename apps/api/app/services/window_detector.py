"""
DEPRECATED: старый window_detector искал параллельные тонкие линии по всему
изображению. Не находил окна (windows = 0), потому что условия слишком строгие.

Заменён на:
- opening_detector.find_openings — gap-based detection вдоль стен
- opening_classifier — gap на ВНЕШНЕЙ стене → window

См. plan_processor.py для нового pipeline.
"""

from app.schemas.geometry import Opening, Wall  # noqa: F401


def detect_windows(*args, **kwargs):
    """DEPRECATED — используйте opening_detector + opening_classifier."""
    raise DeprecationWarning(
        "window_detector.detect_windows() удалён. "
        "Используйте opening_detector.find_openings() + "
        "opening_classifier.classify_openings()."
    )
