from datetime import datetime, date
import requests
import json


def checkResults(YOUR_POSTCODE):

    response = requests.get('https://pickmypostcode.com/api/index.php/entry/').json()

    drawResults = response['data']['drawResults']
    
    mainDraw = drawResults['main']['result']
    surveyDraw = drawResults['survey']['result']
    videoDraw = drawResults['video']['result']
    stackpotDraw = drawResults['stackpot']['result']
    bonusDrawFive = drawResults['bonus']['five']['result']
    bonusDrawTen = drawResults['bonus']['ten']['result']
    bonusDrawTwenty = drawResults['bonus']['twenty']['result']
    miniDraw = drawResults['mini']['result']

    hasWon = any([mainDraw == YOUR_POSTCODE, surveyDraw == YOUR_POSTCODE, videoDraw == YOUR_POSTCODE, YOUR_POSTCODE in stackpotDraw, bonusDrawFive == YOUR_POSTCODE, bonusDrawTen == YOUR_POSTCODE, bonusDrawTwenty == YOUR_POSTCODE, miniDraw == YOUR_POSTCODE])
    results = {
        'hasWon': hasWon,
        'drawResults': {
            'mainDraw': {
                'hasWon': mainDraw == YOUR_POSTCODE,
                'winningPostcode': mainDraw
                },
            'surveyDraw': {
                'hasWon': surveyDraw == YOUR_POSTCODE,
                'winningPostcode': surveyDraw
                },
            'videoDraw': {
                'hasWon': videoDraw == YOUR_POSTCODE,
                'winningPostcode': videoDraw
                },
            'stackpotDraw': {
                'hasWon': YOUR_POSTCODE in stackpotDraw,
                'winningPostcode': stackpotDraw
                },
            'bonusDrawFive': {
                'hasWon': bonusDrawFive == YOUR_POSTCODE,
                'winningPostcode': bonusDrawFive
                },
            'bonusDrawTen': {
                'hasWon': bonusDrawTen == YOUR_POSTCODE,
                'winningPostcode': bonusDrawTen
                },
            'bonusDrawTwenty': {
                'hasWon': bonusDrawTwenty == YOUR_POSTCODE,
                'winningPostcode': bonusDrawTwenty
                },
            'miniDraw': {
                'hasWon': miniDraw == YOUR_POSTCODE,
                'winningPostcode': miniDraw
                }
        }
    }


    # Update database with current results & remove data older than 10 days
    with open('pastData.json') as f:
        pastData = json.load(f)
        pastData[str(date.today())] = results

        dataToDelete = []
        for index, dateStr in enumerate(pastData.keys()):
            if index != 0:
                if (date.today() - datetime.strptime(dateStr, '%Y-%m-%d').date()).days >= 10:
                    dataToDelete.append(dateStr)
        for key in dataToDelete:
            del pastData[key]

    with open('pastData.json', 'w') as f:
        json.dump(pastData, f, indent=2)

    return results