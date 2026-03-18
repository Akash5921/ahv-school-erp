from __future__ import annotations

from calendar import month_abbr
from datetime import date
from decimal import Decimal


def month_labels(*, end_date: date, months: int = 6):
    labels = []
    year = end_date.year
    month = end_date.month
    for _ in range(months):
        labels.append((year, month, f"{month_abbr[month]} {str(year)[-2:]}"))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    labels.reverse()
    return labels


def build_line_chart(*, labels, values, width=420, height=180):
    if not labels:
        return {'has_data': False, 'points': '', 'labels': [], 'values': []}

    safe_values = [float(value or 0) for value in values]
    max_value = max(safe_values) if safe_values else 0
    if max_value <= 0:
        max_value = 1

    pad_left = 24
    pad_right = 24
    pad_top = 18
    pad_bottom = 28
    usable_width = max(width - pad_left - pad_right, 1)
    usable_height = max(height - pad_top - pad_bottom, 1)

    if len(labels) == 1:
        step_x = 0
    else:
        step_x = usable_width / (len(labels) - 1)

    points = []
    rendered_labels = []
    rendered_values = []
    for index, label in enumerate(labels):
        value = safe_values[index]
        x = pad_left + (index * step_x)
        y = pad_top + usable_height - ((value / max_value) * usable_height)
        points.append(f"{x:.1f},{y:.1f}")
        rendered_labels.append({
            'text': label,
            'x': f"{x:.1f}",
            'y': str(height - 6),
        })
        rendered_values.append({
            'text': f"{value:.0f}",
            'x': f"{x:.1f}",
            'y': f"{max(y - 8, 12):.1f}",
        })

    return {
        'has_data': any(safe_values),
        'points': ' '.join(points),
        'labels': rendered_labels,
        'values': rendered_values,
        'width': width,
        'height': height,
        'baseline_y': str(height - pad_bottom),
    }


def build_bar_chart(items, *, max_height=120):
    safe_items = list(items)
    max_value = max((float(item.get('value', 0) or 0) for item in safe_items), default=0)
    if max_value <= 0:
        max_value = 1

    bars = []
    for item in safe_items:
        value = float(item.get('value', 0) or 0)
        bars.append({
            'label': item.get('label', '-'),
            'sub_label': item.get('sub_label', ''),
            'value': item.get('value', 0),
            'height': max(int((value / max_value) * max_height), 8 if value else 0),
        })
    return bars


def build_pie_chart(segments):
    palette = ['#2563eb', '#f59e0b', '#10b981', '#ef4444']
    safe_segments = []
    total = Decimal('0.00')
    for index, segment in enumerate(segments):
        value = Decimal(str(segment.get('value', 0) or 0))
        total += value
        safe_segments.append({
            'label': segment.get('label', '-'),
            'value': value,
            'color': segment.get('color') or palette[index % len(palette)],
        })

    if total <= 0:
        style = 'conic-gradient(#cbd5e1 0 100%)'
        rendered = [{'label': row['label'], 'value': row['value'], 'color': row['color'], 'percent': 0} for row in safe_segments]
        return {'style': style, 'segments': rendered}

    current = Decimal('0.00')
    gradients = []
    rendered = []
    for row in safe_segments:
        percent = (row['value'] / total) * Decimal('100')
        start = current
        current += percent
        gradients.append(f"{row['color']} {start:.2f}% {current:.2f}%")
        rendered.append({
            'label': row['label'],
            'value': row['value'],
            'color': row['color'],
            'percent': round(float(percent), 2),
        })

    return {
        'style': f"conic-gradient({', '.join(gradients)})",
        'segments': rendered,
    }
