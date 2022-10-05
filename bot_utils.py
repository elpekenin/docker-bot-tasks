import config
from contextlib import suppress
from datetime import datetime
import pymongo
from pymongo import MongoClient
import telegram
import telegram.ext
from telegram import *
import time
import typing
from typing import Any, Union


Cursor = typing.NewType('Cursor', pymongo.cursor.Cursor)
Timezone = typing.NewType('Timezone', str)


# # # # # # # # # # # # ============================ # # # # # # # # # # # #
# # # # # # # # # # # # ============ DB ============ # # # # # # # # # # # #
# # # # # # # # # # # # ============================ # # # # # # # # # # # #

def create_user(database: MongoClient, user_id: int, language: str='English', admin: bool=False):
    database['users'].insert_one({
            'user_id': int(user_id),
            'language': language,
            'admin': admin,
            'reports': 0
    })


def set_admin(database: MongoClient, user_id: int, value: bool=False):
    database['users'].update_one(
        {'user_id': int(user_id)},
        {'$set': {'admin': value}}
    )


def save_task(database: MongoClient, group_id: int, message_id: int, user_id: int, location_id: int, longitude: float, latitude: float, reward: str, pokestop: str):
    # Get group's timezone
    timezone = get_attr(
        database,
        group_id,
        'timezone',
        'groups'
    )

    # Save task info
    if pokestop:
        database['reports'].insert_one({
                'group_id': group_id,
                'message_id': message_id,
                'location_id': location_id,
                'longitude': longitude,
                'latitude': latitude,
                'reward': reward,
                'timezone': timezone,
                'pokestop': pokestop
        })

    else:
         database['reports'].insert_one({
                'group_id': group_id,
                'message_id': message_id,
                'location_id': location_id,
                'longitude': longitude,
                'latitude': latitude,
                'reward': reward,
                'timezone': timezone
        })

    # Add 1 to user's reports
    database['users'].update_one(
        {'user_id': int(user_id)},
        {'$inc': {'reports': 1}}
    )

    # # Add 1 to reward's counter
    # database['reports_counter'].update_one(
    #     {'pokemon': reward},
    #     {'$inc': {'reports': 1}}
    # )


def save_unconfirmed(database: MongoClient, group_id: int, message_id: int, location_id: int):
    # Get group's timezone
    timezone = get_attr(
        database,
        group_id,
        'timezone',
        'groups'
    )

    database['reports'].insert_one({
        'group_id': group_id,
        'message_id': message_id,
        'location_id': location_id,
        'reward': 'unconfirmed',
        'timezone': timezone
    })      
    

def read_reports(database: MongoClient, group_id: int, reward: str) -> Cursor:
    return database['reports'].find({
            'group_id': group_id,
            'reward': reward
        },
        {
            '_id': False,
        }
    )
    

def delete_report(database: MongoClient, bot: Bot, delete_id: int, group_id: int):
    report = database['reports'].find({'group_id': group_id, 'message_id': delete_id}, {'_id': False})
    if report.count() == 0:
        report = database['reports'].find_one({'group_id': group_id, 'location_id': delete_id}, {'_id': False})
    else:
        report = report.next()

    with suppress(Exception):
        # Delete bot message
        bot.delete_message(
            chat_id=group_id,
            message_id=report['message_id'],
        )

    with suppress(Exception):
        # Delete location
        bot.delete_message(
            chat_id=group_id,
            message_id=report['location_id']
        )

    # Delete report
    database['reports'].delete_many(
        {
            'group_id': group_id,
            'message_id': delete_id
        }
    )

    database['reports'].delete_many(
        {
            'group_id': group_id,
            'location_id': delete_id
        }
    )


def delete_reports(database: MongoClient, timezone: Timezone, bot: Bot):
    messages = database['reports'].find({'timezone': timezone})
    for message in messages:
        with suppress(Exception):
            # Delete bot message
            bot.delete_message(
                chat_id=message['group_id'],
                message_id=message['message_id']
            )

        with suppress(Exception):
            # Delete location
            bot.delete_message(
                chat_id=message['group_id'],
                message_id=message['location_id']
            )
    
    # Send warnings
    sent = [] 
    for id in messages.distinct('group_id'):
        message = bot.send_message(
            text='⏰💥',
            chat_id=id,
            reply_markup=ReplyKeyboardRemove()
        )
        sent.append(message)

    # Delete warnings    
    time.sleep(5)
    for message in sent:
        with suppress(Exception):
            bot.delete_message(
                chat_id=message.chat_id,
                message_id=message.message_id
            )

    # Delete reports
    database['reports'].delete_many({'timezone': timezone})


def delete_event(database: MongoClient):
    database['tasks'].delete_many({'event': True})
    database['multi_tasks'].delete_many({'event': True})
    

def create_group(database: MongoClient, group_id: int, language: str, pokestop: bool, timezone: Timezone, confirmation: bool):
    if(timezone[:3] == 'GMT'):
        database['groups'].insert_one({
            'group_id': int(group_id),
            'language': language,
            'pokestop': pokestop,
            'timezone': timezone,
            'confirmation' : confirmation
        })
        return

    raise Exception(f"'{timezone}' isn't a valid timezone")


def edit_group(database: MongoClient, group_id: int, language: str, pokestop: bool, timezone: Timezone, confirmation: bool):
    database['groups'].update_one(
        {'group_id': int(group_id)},
        {
            '$set':{
                'language': language,
                'pokestop': pokestop,
                'timezone': timezone,
                'confirmation': confirmation
            }
        }
    )


def get_attr(database: MongoClient, id: int, attribute: str='language', collection: str='users') -> Any:
    key = collection[:-1] + '_id'
    results = list(
        database[collection].find(
            {
                key: int(id)
            },
            {
                '_id': False,
                attribute: True
            }
        )
    )
    length = len(results)

    if(length == 0):
        raise Exception(f"'{key}'={id} not found on {collection}")
        return

    if(length > 1):
        raise Exception(f"'{key}'={id} wasn't unique on {collection}")
        return
        
    return results[0][attribute]


def get_languages(database: MongoClient) -> [str]:    
    return list(database['texts'].find({}, {'_id': False}).distinct('language'))


def get_categories(database: MongoClient, language: str) -> [str]:
    return database['tasks'].find(
        {},
        {
            '_id': False,
            f'{language}.category': True
        }
    ).distinct(f'{language}.category')


def get_available_rewards(database: MongoClient, language: str='English') -> [str]:
    return database['tasks'].find(
            {},
            {
                '_id': False,
                f'{language}.reward': True
            }
    ).distinct(f'{language}.reward')


def get_tasks(database: MongoClient, category: str, language: str='English') -> [dict]:
    tasks = database['tasks'].find(
            {
                f'{language}.category': category
            },
            {
                '_id': False,
                f'{language}.task': True,
                f'{language}.reward': True,
                'cp': True,
                'shiny': True
            }
    )
    multiples = database['multi_tasks'].find(
            {
                f'{language}.category': category
            },
            {
                '_id': False,
                f'{language}.task': True,
                f'{language}.reward': True,
                'cp': True,
                'shiny': True
            }
    )
    array = []
    for task in multiples:
        text = ""
        for i in range(len(task[language]['reward'])):
            text += f"{task[language]['reward'][i] + ('✨' if task['shiny'][i]==True else '')}/"
        text = text[:-1]
        text += f", {task[language]['task']}"
        array.append(text)
    array.extend([f"{task[language]['reward'] + ('✨' if task['shiny']==True else '')}, {task[language]['task']}\n💯: {task['cp']}" for task in tasks]) 
    array.append("❌❌❌")
    return array


def get_text(database: MongoClient, language: str, text:str) -> str:
    return database['texts'].find_one(
        {'language': language},
        {
            '_id': False,
            text : True
        }
        )[text]


def get_commands(database: MongoClient, language: str) -> [str]:
    for dictionary in database['commands'].find({},{'_id': False}):
        for key, value in dictionary.items():
            if key == language:
                return value
        
    return "Error loading commands"


def get_private_button(database: MongoClient, language: str) -> InlineKeyboardMarkup:
    button_text = get_text(database, language, 'private')
    keyboard = [[InlineKeyboardButton(button_text, url='https://t.me/elpekebot')]]
    return InlineKeyboardMarkup(keyboard)


# # # # # # # # # # # # ============================ # # # # # # # # # # # #
# # # # # # # # # # # # ============ ANY =========== # # # # # # # # # # # #
# # # # # # # # # # # # ============================ # # # # # # # # # # # #


def get_midnight() -> Timezone:
    now = datetime.utcnow()
    if (now.minute < 55 and now.minute > 5):
        return False 

    tz = 24-now.hour
    if(tz > 14):
        tz -= 24
        
    return f'GMT+{tz}' if tz > 0 else f'GMT{tz}'


def get_timezones() -> [Timezone]:
    timezones = []
    for tz in range(-12, 15):
        timezones.append(f'GMT+{tz}' if tz > 0 else f'GMT{tz}')
    return timezones


def array_to_keyboard(array: [str], selective: bool=True) -> ReplyKeyboardMarkup:
    return telegram.ReplyKeyboardMarkup(
        [[element] for element in array],
        one_time_keyboard=True,
        selective=selective
    )


def delete_keyboard(database: MongoClient, bot: Bot):
    groups = database['groups'].find(
        {},
        {
            '_id': False,
            'group_id': True
        }
    )

    for group in groups:
        sent = bot.send_message(
            text="Deleting keyboards...",
            chat_id=group['group_id'],
            reply_markup=ReplyKeyboardRemove()
        )

        bot.delete_message(
            chat_id=group['group_id'],
            message_id=sent.message_id
        )
                

if __name__ == '__main__':
    print("You shouldn't be executing this")
