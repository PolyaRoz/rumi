"""
DEPRECATED: старый door_detector использовал HoughCircles по всему изображению,
что вызывало 64 ложных детекта (арки от санитарной мебели, плиты, раковин).

Заменён на:
- opening_detector.find_openings — gap-based detection ВДОЛЬ найденных стен
- opening_classifier.classify_openings — классификация openings в door/window

См. plan_processor.py для нового pipeline.
"""

# Backwards-compat shim — на случай если кто-то ещё импортирует
from app.schemas.geometry import Opening, Wall  # noqa: F401


def detect_doors(*args, **kwargs):
    """DEPRECATED — используйте opening_detector + opening_classifier."""
    raise DeprecationWarning(
        "door_detector.detect_doors() удалён. "
        "Используйте opening_detector.find_openings() + "
        "opening_classifier.classify_openings()."
    )
