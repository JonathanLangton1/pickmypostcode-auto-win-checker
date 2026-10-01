from datetime import timedelta
from draws import DRAWS


def summariseWeeklyResults(history, sunday):
    """Return (text, html) summarising every draw from Monday to `sunday`."""
    days = [sunday - timedelta(days=offset) for offset in range(6, -1, -1)]
    readings = [(day, [(draw, history.result(day, draw)) for draw in DRAWS]) for day in days]
    total_wins = any(result and result.hasWon for _, row in readings for _, result in row)
    unchecked = sum(result is None for _, row in readings for _, result in row)
    incomplete = (f"{unchecked} of {len(days) * len(DRAWS)} draws weren't checked, so this week's results are incomplete."
                  if unchecked else "")

    text_lines = []
    weekly_summary = []
    for day, row in readings:
        text_lines.append(day.strftime('%A, %Y-%m-%d'))
        formatted_result = f"""
            <tr>
                <td style="padding: 15px; border-bottom: 1px solid #e0e0e0; vertical-align: top; font-size: 14px;">
                    {day.strftime('%A, %Y-%m-%d')}
                </td>
                <td style="padding: 15px; border-bottom: 1px solid #e0e0e0; vertical-align: top; font-size: 14px;">
            """
        for draw, result in row:
            status, colour = _status(result)
            winning_postcode = result.winningText() if result else '—'
            text_lines.append(f"  {draw.label}: {status} ({winning_postcode})")
            formatted_result += f"""
                <div style="margin-bottom: 10px; padding: 10px; background-color: #f9f9f9; border-radius: 5px;">
                    <strong style="font-size: 16px;">{draw.label}:</strong><br>
                    <span style="color: {colour}; font-weight: bold;">
                        Has Won: {status}
                    </span><br>
                    <span style="font-size: 14px;">Winning Postcode: {winning_postcode}</span>
                </div>
                """
        formatted_result += "</td></tr>"
        weekly_summary.append(formatted_result)

    if total_wins:
        verdict_text = "You had a win this week! 🎉"
        verdict_html = "<strong>Congratulations!</strong> You had a win this week! 🎉"
    elif unchecked:
        verdict_text = verdict_html = "No wins were recorded this week."
    else:
        verdict_text = verdict_html = "Unfortunately, you didn't have any wins this week. Better luck next week!"
    if incomplete:
        verdict_text += " " + incomplete
        verdict_html += " " + incomplete
    text = "Hey 👋,\n\n" + verdict_text + "\n\n" + "\n".join(text_lines) + "\n\nThanks,\nRobot"

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
            <div style="background-color: #4CAF50; color: #ffffff; padding: 15px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">Weekly Postcode Results</h1>
            </div>
            <div style="padding: 20px;">
                <p style="font-size: 16px; margin-bottom: 20px;">Hey 👋,</p>
                <p style="font-size: 16px; margin-bottom: 20px;">
                    {verdict_html}
                </p>
                <p style="font-size: 16px; margin-bottom: 20px;">Here are the results for each day:</p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <thead>
                        <tr>
                            <th style="padding: 10px; background-color: #f4f4f4; text-align: left; font-size: 16px; border-bottom: 2px solid #e0e0e0;">Date</th>
                            <th style="padding: 10px; background-color: #f4f4f4; text-align: left; font-size: 16px; border-bottom: 2px solid #e0e0e0;">Results</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(weekly_summary)}
                    </tbody>
                </table>
                <p style="font-size: 16px;">Thanks,<br>Robot</p>
            </div>
        </div>
    </body>
    </html>
    """

    return text, html


def _status(result):
    if result is None:
        return 'Not checked', '#999'
    if result.hasWon:
        return ('Yes (claimed)' if result.claimed else 'Yes'), '#4CAF50'
    return 'No', '#F44336'
