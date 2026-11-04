from datetime import datetime


MAX_TEACHER_ACTIVE_SECONDS = 300
MINIMUM_PRECISION = 0.85
MINIMUM_RECALL = 0.80


def _validate_confusion_count(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} debe ser un entero no negativo.")


def calculate_precision(true_positives: int, false_positives: int) -> float:
    """Calculate VP / (VP + FP) for the LLM technology extraction."""
    _validate_confusion_count(true_positives, "VP")
    _validate_confusion_count(false_positives, "FP")

    denominator = true_positives + false_positives
    if denominator == 0:
        raise ValueError("La precisión requiere al menos una predicción positiva.")

    return true_positives / denominator


def calculate_recall(true_positives: int, false_negatives: int) -> float:
    """Calculate VP / (VP + FN) for the LLM technology extraction."""
    _validate_confusion_count(true_positives, "VP")
    _validate_confusion_count(false_negatives, "FN")

    denominator = true_positives + false_negatives
    if denominator == 0:
        raise ValueError("El recall requiere al menos un caso positivo real.")

    return true_positives / denominator


def meets_precision_target(true_positives: int, false_positives: int) -> bool:
    return calculate_precision(true_positives, false_positives) >= MINIMUM_PRECISION


def meets_recall_target(true_positives: int, false_negatives: int) -> bool:
    return calculate_recall(true_positives, false_negatives) >= MINIMUM_RECALL


def teacher_active_time_seconds(opened_at: datetime, decision_at: datetime) -> float:
    """Return active review time between opening a project and recording a decision."""
    if not isinstance(opened_at, datetime) or not isinstance(decision_at, datetime):
        raise TypeError("Las marcas de tiempo deben ser objetos datetime.")

    elapsed_seconds = (decision_at - opened_at).total_seconds()
    if elapsed_seconds < 0:
        raise ValueError("La decisión no puede ser anterior a la apertura del proyecto.")

    return elapsed_seconds


def meets_teacher_time_target(opened_at: datetime, decision_at: datetime) -> bool:
    return teacher_active_time_seconds(opened_at, decision_at) <= MAX_TEACHER_ACTIVE_SECONDS
