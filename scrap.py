from bs4 import BeautifulSoup
import config
from contextlib import suppress
from pymongo import MongoClient
import pypokedex
import re
from requests import get


if config.db_uri:
    client = MongoClient(config.db_uri, serverSelectionTimeoutMS=5000)
else:
    client = MongoClient(
        config.db_ip,
        username=config.db_user,
        password=config.db_pass,
        authSource=config.db_auth
    )
database = client['bot']

#Translation check
def translate(text: str, language: str = 'Español') -> str:
    translation = database['translations'].find_one({'text': text}, {language: True})
    if (translation is not None):
        return translation[language]

    else: 
        translation = input(f"Traduce el siguiente texto: {text}\n")
        database['translations'].insert_one({
            'text': text,
            language : translation
        })
        return translation

#Get master div wrapper
response = get('https://thesilphroad.com/research-tasks')
soup = BeautifulSoup(response.text, 'html.parser')
divWrapper = soup.find('div', {'id':'taskGroupWraps'})
groupDivs = divWrapper.find_all('div', recursive=False)

#Delete database
database['tasks'].delete_many({})
database['multi_tasks'].delete_many({})

#Iterate over categories
for groupDiv in groupDivs:  
    category = groupDiv.find_all()[0]
    category = ' '.join(category.text.split(' ')[:-1])
    tasksDivs = groupDiv.find_all('div', {'class' : re.compile('.*task unconfirmed pkmn.*')}, recursive=False)

    #Iterate over tasks
    for taskDiv in tasksDivs:
        with suppress(Exception):
            task = taskDiv.find('p', {'class': 'taskText'}).text[:-1]
            wrapper = taskDiv.find('div', {'class': 'taskRewardsWrap'})

            #Iterate over rewards
            rewardsDiv = wrapper.find_all('div', {'class' : re.compile('.*task-reward pokemon.*')}, recursive=False)
            if(len(rewardsDiv) == 0): 
                continue                        
            cps = [int(div.find_all('div', class_='cp')[1].find_all('p')[1].text.replace(",","")) for div in rewardsDiv]
            rewards = [
                pypokedex.get(dex=int(div.find('img')['src'].split('/')[-1].split('.')[0])).name.capitalize() #convert from dexnumber to name
                if '-' not in div.find('img')['src'].split('/')[-1].split('.')[0]    #this handles alolan/galarian forms
                else div.find('img')['src'].split('/')[-1].split('.')[0].capitalize()  #this handles alolan/galarian forms
                for div in rewardsDiv
            ]
            shinys = ['shinyAvailable' in div['class'] for div in rewardsDiv]

            #Save rewards on database 
            for (cp, reward, shiny) in zip(cps, rewards, shinys):
                database['tasks'].insert_one({
                    'cp' : cp,
                    'shiny' : shiny,
                    'event' : True if (category.lower() == 'event') else False,
                    'English' : {
                        'category' : category.capitalize(),
                        'task' : task.capitalize(),
                        'reward' : reward.capitalize()
                    },
                    'Español' : {
                        'category' : translate(category.capitalize()),
                        'task' : translate(task.capitalize()),
                        'reward' : reward.capitalize()
                    }
                })            
            if(len(cps) > 1):
                database['multi_tasks'].insert_one({
                    'shiny' : shinys,
                    'event' : True if (category.lower() == 'event') else False,
                    'English' : {
                        'category' : category.capitalize(),
                        'task' : task.capitalize(),
                        'reward' : rewards
                    },
                    'Español' : {
                        'category' : translate(category.capitalize()),
                        'task' : translate(task.capitalize()),
                        'reward' : rewards
                    }
                })
    
