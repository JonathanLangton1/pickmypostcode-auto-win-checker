from datetime import timedelta
from draws import DRAWS
from emails import weeklyEmail
from emailTemplate import render


def summariseWeeklyResults(history, sunday):
    """Return (text, html) summarising every draw from Monday to `sunday`."""
    days = [sunday - timedelta(days=offset) for offset in range(6, -1, -1)]
    readings = [(day, [(draw, history.result(day, draw)) for draw in DRAWS]) for day in days]
    total_wins = any(result and result.hasWon for _, row in readings for _, result in row)
    unchecked = sum(result is None for _, row in readings for _, result in row)
    incomplete = (f"{unchecked} of {len(days) * len(DRAWS)} draws weren't checked, so this week's results are incomplete."
                  if unchecked else "")

    text_lines = []
    for day, row in readings:
        text_lines.append(day.strftime('%A, %Y-%m-%d'))
        for draw, result in row:
            winning_postcode = result.winningText() if result else '-'
            text_lines.append(f"  {draw.label}: {_status(result)} ({winning_postcode})")

    if total_wins:
        verdict_text = "You had a win this week! 🎉"
        verdict_html = "Congratulations, you had a win this week."
    elif unchecked:
        verdict_text = verdict_html = "No wins were recorded this week."
    else:
        verdict_text = verdict_html = "Unfortunately, you didn't have any wins this week. Better luck next week!"
    if incomplete:
        verdict_text += " " + incomplete
        verdict_html += " " + incomplete
    text = "Hey 👋,\n\n" + verdict_text + "\n\n" + "\n".join(text_lines) + "\n\nThanks,\nRobot"
    return text, render(weeklyEmail(history, sunday, verdict_html))


def _status(result):
    if result is None:
        return 'Not checked'
    if result.hasWon:
        return 'Yes (claimed)' if result.claimed else 'Yes'
    return 'No'
