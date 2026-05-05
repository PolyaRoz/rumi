"""
DEPRECATED: старый room_detector выдавал rooms=0 потому что не закрывал
дверные проёмы перед flood fill — комнаты "вытекали" друг в друга.

Заменён на:
- room_polygonizer.polygonize_rooms — закрытие door gaps + flood fill + contours

См. plan_processor.py для нового pipeline.
"""

from app.schemas.geometry import Room, Wall  # noqa: F401


def detect_rooms(*args, **kwargs):
    """DEPRECATED — используйте room_polygonizer.polygonize_rooms()."""
    raise DeprecationWarning(
        "room_detector.detect_rooms() удалён. "
        "Используйте room_polygonizer.polygonize_rooms()."
    )


def assign_room_labels_from_ocr(rooms, ocr_areas):
    """Сохранён для совместимости — функциональность полезная."""
    import logging
    import math
    logger = logging.getLogger(__name__)

    for area_m2, cx, cy in ocr_areas:
        if not rooms:
            break
        best_room = min(
            rooms,
            key=lambda r: (
                (r.centroid.x - cx) ** 2 + (r.centroid.y - cy) ** 2
                if r.centroid else float("inf")
            ),
        )
        if best_room.area_m2 is None:
            best_room.area_m2 = area_m2
            logger.debug(f"OCR: {best_room.id} ← {area_m2} м²")

    return rooms
