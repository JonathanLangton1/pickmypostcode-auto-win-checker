from datetime import datetime, date, timedelta
import json
import os

def summariseWeeklyResults(YOUR_POSTCODE):
    dir = os.path.dirname(__file__)
    with open(f'{dir}/pastData.json') as f:
        pastData = json.load(f)

    today = date.today()
    week_ago = today - timedelta(days=7)

    weekly_summary = []
    total_wins = False

    for day, result in pastData.items():
        if day == "lastBrowserLogin":
            continue  # Skip the 'lastBrowserLogin' key

        try:
            day_date = datetime.strptime(day, '%Y-%m-%d').date()
        except ValueError as e:
            print(f"Skipping invalid date entry: {day}")
            continue  # Skip any invalid date entries

        if week_ago <= day_date <= today:
            if result['hasWon']:
                total_wins = True

            formatted_result = f"""
            <tr>
                <td style="padding: 15px; border-bottom: 1px solid #e0e0e0; vertical-align: top; font-size: 14px;">
                    {day_date.strftime('%A, %Y-%m-%d')}
                </td>
                <td style="padding: 15px; border-bottom: 1px solid #e0e0e0; vertical-align: top; font-size: 14px;">
            """
            for draw, details in result['drawResults'].items():
                winning_postcode = (
                    ', '.join(details['winningPostcode'])
                    if isinstance(details['winningPostcode'], list)
                    else details['winningPostcode']
                )
                formatted_result += f"""
                <div style="margin-bottom: 10px; padding: 10px; background-color: #f9f9f9; border-radius: 5px;">
                    <strong style="font-size: 16px;">{draw.replace('Draw', '').capitalize()}:</strong><br>
                    <span style="color: {'#4CAF50' if details['hasWon'] else '#F44336'}; font-weight: bold;">
                        Has Won: {'Yes' if details['hasWon'] else 'No'}
                    </span><br>
                    <span style="font-size: 14px;">Winning Postcode: {winning_postcode}</span>
                </div>
                """
            formatted_result += "</td></tr>"
            weekly_summary.append(formatted_result)

    summary = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
            <div style="background-color: #4CAF50; color: #ffffff; padding: 15px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">Weekly Postcode Results</h1>
            </div>
            <div style="padding: 20px;">
                <p style="font-size: 16px; margin-bottom: 20px;">Hey 👋,</p>
                <p style="font-size: 16px; margin-bottom: 20px;">
                    {'<strong>Congratulations!</strong> You had a win this week! 🎉' if total_wins else "Unfortunately, you didn't have any wins this week. Better luck next week!"}
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

    return summary