import bot_utils
import config
from contextlib import suppress
from datetime import datetime
import logging
from pymongo import MongoClient
import telegram
from telegram.ext import *
from telegram import *
import time 
import typing
from typing import Any, Union


logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
)
logger = logging.getLogger(__name__)

token = config.token 
updater = Updater(token)
dp = updater.dispatcher
bot = telegram.Bot(token)

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

sleep = 5 
parse_mode = "HTML"


class my_location:
    latitude = longitude = 0

    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude


def check_user(update: Update, context: CallbackContext) -> [int, Union[bool, str]]:
    try:
        user_id = int(update.message.from_user.id)
    except Exception:
        user_id = int(update.callback_query.from_user.id)

    with suppress(Exception):
        return user_id, bot_utils.get_attr(database, user_id)

    return user_id, False


def check_admin(update: Update, context: CallbackContext, user_id: int) -> bool:
    member = bot.get_chat_member(
        chat_id=update.effective_chat.id,
        user_id=update.message.from_user.id
    )
    status = member.status
    if (status == "creator" or status == "administrator"): 
        return True

    return False


def check_group_values(update: Update, context: CallbackContext, language: str, pokestop: str, timezone: str) -> bool:
    languages = bot_utils.get_languages(database)
    if language not in languages:
        update.message.reply_text('Invalid language, available languages:\n' + "\n".join([lang for lang in languages]))
        return False

    if (not isinstance(pokestop, bool)):
        update.message.reply_text("Pokestop has to be '0'(False), '1'(True), 'True' or 'False'")
        return False

    if timezone not in bot_utils.get_timezones():
        update.message.reply_text(
            "Timezone has to be in format 'GMTX'\n" + "Check possible values with <code>/get_timezones</code>",
            parse_mode=parse_mode
        )  
        return False

    return True  


def check_group_exists(update: Update, context: CallbackContext) -> Union[bool, str]:
    with suppress(Exception):
        return bot_utils.get_attr(
            database,
            id=update.effective_chat.id,
            collection='groups'
        )

    return False


def get_timezones(update: Update, context: CallbackContext):
    timezones = bot_utils.get_timezones()
    update.message.reply_text(
        ",".join([f"<code>{timezone}</code>" for timezone in timezones]),
        parse_mode=parse_mode
    )  


def get_rewards(update: Update, context: CallbackContext):
    user_id, language = check_user(update, context)

    # If user isn't registered, tell them to do so
    if not language:
        set_lang_start(update, context)
        return

    rewards = bot_utils.get_available_rewards(
        database,
        language
    )

    update.message.reply_text(
        ",".join([f"<code>{reward}</code>" for reward in rewards]),
        parse_mode=parse_mode
    )

  
def get_reports(update: Update, context: CallbackContext):
    group_id = update.effective_chat.id
    language = check_group_exists(update, context)    
    reward = update.message.text.split(" ")[1]
    check = False
    try:
        if update.message.text.split(" ")[2] == "1":
            check = True
        
    except Exception:
        pass

    id = update.message.message_id

    # Unknown reward
    if reward not in bot_utils.get_available_rewards(database, language):
        update.message.reply_text(
            bot_utils.get_text(database, language, "unknown_reward"),
            parse_mode=parse_mode
        )
        time.sleep(sleep)
        remove_messages(update, context, [id, id+1])
        return

    # Send messages
    with suppress(Exception):
        reports = bot_utils.read_reports(database, group_id, reward)

        if reports.count() == 0:
            update.message.reply_text(
                bot_utils.get_text(database, language, 'no_reports')
            )
            time.sleep(sleep)
            remove_messages(update, context, [id, id+1])
            return

        bot.send_message(
            text=f"{reward}:",
            chat_id=update.message.from_user.id,
        )
        for report in reports:
            # Send location
            bot.send_location(
                chat_id=update.message.from_user.id,
                longitude=report['longitude'],
                latitude=report['latitude']
            )

            # Send pokestop
            with suppress(Exception):
                bot.send_message(
                    text=f"{report['pokestop']}",
                    chat_id=update.message.from_user.id,
                    parse_mode=parse_mode
                )

            # Send coordinates
            if check:
                bot.send_message(
                    text=f"<code>{report['latitude']}, {report['longitude']}</code>",
                    chat_id=update.message.from_user.id,
                    parse_mode=parse_mode
                )
                
        remove_messages(update, context, [id])
        return

    # If messages can't be sent, tell the user to open conv
    update.message.reply_text(
        bot_utils.get_text(database, language, "open_private"),
        reply_markup=bot_utils.get_private_button(database, language)
    )
    time.sleep(sleep)
    remove_messages(update, context, [id, id+1])


def remove_messages(update: Update, context: CallbackContext, ids: [int]):
    for id in ids:
        with suppress(Exception):
            bot.deleteMessage(
                chat_id=update.effective_chat.id,
                message_id=id
            )


def error_callback(update: Update, context: CallbackContext):
    logger.warning(f'Update: "{update}" caused error: "{context.error}"')


def start(update: Update, context: CallbackContext):
    user_id, language = check_user(update, context)

    # If user isn't registered, tell them to do so
    if not language:
        set_lang_start(update, context)
        return
       
    # If registered, help text
    update.message.reply_text(
        bot_utils.get_text(database, language, 'start_reg')
    ) 


def help(update: Update, context: CallbackContext):
    user_id, language = check_user(update, context)

    if not language:
        set_lang_start(update, context)
        return
    
    commands = bot_utils.get_commands(database, language)
    update.message.reply_text(
        '\n'.join(commands),
        parse_mode=parse_mode
    )


def delete_event(update: Update, context: CallbackContext):
    if update.message.from_user.username == config.username:
        bot_utils.delete_event(database)
        update.message.reply_text("Done")
        return
    update.message.reply_text("You can't do that")
    bot.send_message(
        text=f"WARNING @{update.message.from_user.username} tried to delete event",
        chat_id=354728208
    )
        

def delete_timezone(update: Update, context: CallbackContext):
    if update.message.from_user.username == config.username:
        tz = update.message.text.split(' ')[1]
        bot_utils.delete_reports(database, tz, bot)
        update.message.reply_text("Done")
        return
    update.message.reply_text("You can't do that")
    bot.send_message(
        text=f"WARNING @{update.message.from_user.username} tried to delete timezone",
        chat_id=354728208
    )


def delete_report(update: Update, context: CallbackContext):
    with suppress(Exception):
        user_id = update.message.from_user.id
        language = check_group_exists(update, context)
        if not check_admin(update, context, user_id):
            sent = update.message.reply_text(bot_utils.get_text(database, language, 'admin'))
            time.sleep(sleep)
            bot.delete_message(
                chat_id=sent.chat_id,
                message_id=sent.message_id
            )
            return
        
        delete_id = update.message.reply_to_message.message_id
        bot_utils.delete_report(database, bot, delete_id, update.effective_chat.id)
        sent = update.message.reply_text('✅')
        time.sleep(2)
        for id in [sent.message_id, update.message.message_id]:
            with suppress(Exception):
                bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=id
                )
        return

    bot.send_message(
        text="This group isn't registered, check <code>/add_group</code>",
        chat_id=update.effective_chat.id,
        parse_mode=parse_mode
    )   


def set_lang_start(update: Update, context: CallbackContext):
    update.message.reply_text(
        'Select your language',
        reply_markup=bot_utils.array_to_keyboard(bot_utils.get_languages(database))
    )


def set_lang_command(update: Update, context: CallbackContext):
    languages = bot_utils.get_languages(database)
    with suppress(Exception):
        language = update.message.text.split(" ")[1]
        language = language[0].upper() + language[1:].lower()
        if language not in languages:
            update.message.reply_text(
                "Usage:\n<i>/set_lang language</i>\n\nAvailable languages are:\n" + 
                "\n".join([f'<code>{lang}</code>' for lang in languages]),
                parse_mode=parse_mode
            )
            return
            
        database['users'].update_one(
            {
                'user_id': update.message.from_user.id
            },
            {
                '$set': {'language': language}
            }
        )    
        update.message.reply_text("🤖👍🏻")
        return


    update.message.reply_text(
            "Usage:\n<i>/set_lang language</i>\n\nAvailable languages are:\n" + 
            "\n".join([f'<code>{lang}</code>' for lang in languages]),
            parse_mode=parse_mode
        )
                

def add_group(update: Update, context: CallbackContext):
    # If user isn't admin, can't use the command
    user_id = update.message.from_user.id
    language = check_group_exists(update, context)     
    if not check_admin(update, context, user_id):
        sent = update.message.reply_text(bot_utils.get_text(database, language if language else 'English', 'admin'))
        time.sleep(sleep)
        bot.delete_message(
            chat_id=sent.chat_id,
            message_id=sent.message_id
        )
        return
    
    # Parse values
    with suppress(Exception):
        group_language, pokestop, timezone = update.message.text.split(" ")[1:4]

        try:
            confirmation = update.message.text.split(" ")[4]
        except Exception:
            confirmation = False

        if((pokestop == "0") or (pokestop == "False")):
            pokestop = False
        elif((pokestop == "1") or (pokestop == "True")):
            pokestop = True

        if((confirmation == "0") or (confirmation == "False")):
            confirmation = False
        elif((confirmation == "1") or (confirmation == "True")):
            confirmation = True

        check_values = check_group_values(update, context, group_language, pokestop, timezone)
        check_group = check_group_exists(update, context)

        # If everything is OK, create/edit group
        if check_values:
            # If new group, create it
            if not check_group:
                bot_utils.create_group(
                    database,
                    update.effective_chat.id,
                    group_language,
                    pokestop,
                    timezone,
                    confirmation
                )
                update.message.reply_text("Group created 🤖👍🏻")

                update.message.reply_text("To change configuration, use this command again with the new values")
                return
            
            # Else, edit
            bot_utils.edit_group(
                database,
                update.effective_chat.id,
                group_language,
                pokestop,
                timezone,
                confirmation
            )
            update.message.reply_text("Group configuration updated 🤖👍🏻")
            return
        
        # Values weren't correct
        group_error(update, context)
        return

    group_error(update, context)


def group_error(update: Update, context: CallbackContext):
    update.message.reply_text(
        """Usage: <code>/add_group language pokestop timezone confirmation</code>
-Language: <i>Group's language</i> 
-Pokestop: <i>Reports with or without pokestop name</i> 
-Timezone: <i>Group's timezone, used for 00:00 reset</i>
-Confirmation: <i>Ask confirmation before continuing(use it to avoid problems with other bots, defaults to False)</i>
        
<b>For example: /add_group English 0 GMT+1 or /add_group Español 1 GMT+3 1</b>""",
        parse_mode=parse_mode
    )


def inline_keyboard_handler(update: Update, context: CallbackContext):  
    with suppress(Exception):
        query = update.callback_query
        user_id = query.from_user.id
        username = query.from_user.username 
        group_id = query.message.chat_id
        message_id = query.message.message_id
        language = check_group_exists(update, context)

        reward, longitude, latitude, pokestop_name, location_id = query.data.split(',')  

        # Edit text
        old_text = query.message.text
        rows = old_text.split('\n')
        rows[0] = f"<a href='https://www.google.com/maps/search/?api=1&query={latitude},{longitude}'>{rows[0]}</a>"
        new_row = rows[1].split(',')
        new_row[0] = f"<b>{reward}</b>"
        new_row[1] = f"<i>{new_row[1]}</i>"
        rows[1] = ','.join(new_row)

        new_text_rows = []
        new_text_rows.extend(rows[0:2])
        cp = database['tasks'].find_one(
                {
                    f'{language}.reward': reward.split('✨')[0]
                },
                {
                    '_id': False
                }
            )['cp']

        new_text_rows.append(f'💯: {cp}')
        new_text_rows.append(rows[2])
        new_text_rows.append(f"{bot_utils.get_text(database, language, 'confirmed')} @{username}")
        new_text = '\n'.join(new_text_rows)

        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=message_id,
            text=new_text,
            reply_markup=InlineKeyboardMarkup([]),
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

        bot_utils.save_task(
            database, 
            group_id,
            message_id,
            user_id,
            int(location_id),
            longitude,
            latitude,
            reward.split('✨')[0],
            pokestop_name
        )
        return

    data = update.callback_query.data
    if data == 'continue' or data =='cancel':
        with suppress(Exception):
            bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.callback_query.message.message_id
            )


def default_private_handler(update: Update, context: CallbackContext):
    text = update.message.text
    user_id, language = check_user(update, context)
    languages = bot_utils.get_languages(database)
  
    # If user isn't registered
    if not language:
        # Check if user is setting language
        if text in languages:
            language = text
            bot_utils.create_user(
                database,
                user_id,
                text
            )
            update.message.reply_text(
                bot_utils.get_text(database, language, 'registered'),
		        reply_markup=ReplyKeyboardRemove()
            )
            return
    
        # If not, tell the user to set up language
        update.message.reply_text("Please set up your language with /start")
        return

    # If registered
    update.message.reply_text(
        bot_utils.get_text(database, language, 'default')
    )


# # # # # # # # # # # # ============================ # # # # # # # # # # # #
# # # # # # # # # # # # ======== CONV HANDLER ====== # # # # # # # # # #
# # # # # # # # # # # # ============================ # # # # # # # # # # # #

CATEGORY, POKESTOP, TASK, CONFIRMATION = range(4)
location = []
location_id = 0
pokestop_name = ""
ids = []

conv_state = typing.NewType('state', int)

def coords_location(update: Update, context: CallbackContext) -> conv_state:
    global location, location_id
    # Save location to global variable
    id = update.message.message_id
    ids.append(id)
    location = my_location(
        latitude=update.message.text.split(',')[0],
        longitude=update.message.text.split(',')[1]
    )

    # Send location
    sent = bot.send_location(
        chat_id=update.effective_chat.id,
        latitude=location.latitude,
        longitude=location.longitude
    )

    location_id = sent.message_id

    # Do the rest
    return confirmation(update, context)


def telegram_location(update: Update, context: CallbackContext) -> conv_state:
    global location, location_id
    # Save location to global variable
    id = update.message.message_id
    location_id = id
    location = update.message.location

    # Do the rest
    return confirmation(update, context)


def confirmation(update: Update, context: CallbackContext) -> conv_state:
    group_language = check_group_exists(update, context)
    # Get value
    confirmation = bot_utils.get_attr(
        database,
        id=update.effective_chat.id,
        attribute='confirmation',
        collection='groups'
    )

    # If not confirmation needed, continue with the process
    if not confirmation:
        return reply_to_location(update, context)
    
    confirmation_text = bot_utils.get_text(database, group_language, 'confirmation')
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('✅', callback_data='continue'), InlineKeyboardButton('❌', callback_data='cancel')]])
    sent = update.message.reply_text(
        text=confirmation_text,
        reply_markup=keyboard
    )
    ids.append(sent.message_id)

    return CONFIRMATION


def confirmation_handler(update: Update, context: CallbackContext) -> conv_state:
    query = update.callback_query
    confirmation = query.data
    message_id = query.message.message_id
    ids.append(message_id)

    if confirmation == 'continue':          
        return reply_to_location(update, context)

    return end_conv_handler(update, context)


def reply_to_location(update: Update, context: CallbackContext) -> conv_state:  
    group_language = check_group_exists(update, context) 
    # Save location and id
    global location, ids, location_id
    try:
        id = update.message.message_id
    except Exception:
        id = update.callback_query.message.message_id

    with suppress(Exception):    
        # Check if user is registered
        user_id, user_language = check_user(update, context)   
        if not user_language:
            sent =  bot.send_message(
                text=bot_utils.get_text(database, group_language, "register"),
                chat_id=update.effective_chat.id,
                reply_markup=bot_utils.get_private_button(database, group_language)
            )
            time.sleep(sleep)
            for message_id in [id, sent.message_id]:
                with suppress(Exception):
                    bot.delete_message(
                        message_id=message_id,
                        chat_id = update.effective_chat.id
                    )

            return ConversationHandler.END

        # Continue with pokestop/category            
        pokestop = bot_utils.get_attr(
            database,
            id=update.effective_chat.id,
            attribute='pokestop',
            collection='groups'
        )    

        if pokestop:
            try:
                sent =  update.message.reply_text(
                    text=bot_utils.get_text(database, group_language, 'pokestop'),
                    chat_id=update.effective_chat.id,
                    reply_markup=ReplyKeyboardRemove()
                )

            except Exception:
                sent =  bot.send_message(
                    text=bot_utils.get_text(database, group_language, 'pokestop'),
                    chat_id=update.effective_chat.id,
                    reply_markup=ReplyKeyboardRemove()
                )

            ids.append(sent.message_id)
            return POKESTOP
            
        else:
            return ask_category(update, context)
    
    # If group wasn't registered
    bot.send_message(
        text="This group isn't registered, check <code>/add_group</code>",
        chat_id=update.effective_chat.id,
        parse_mode=parse_mode
    )   
    return ConversationHandler.END


def reply_to_pokestop(update: Update, context: CallbackContext) -> conv_state:
    global pokestop_name
    pokestop_name = update.message.text
    try:
        id = update.message.message_id
    except Exception:
        id = update.callback_query.message.message_id
        
    ids.append(id)
    return ask_category(update, context)


def ask_category(update: Update, context: CallbackContext) -> conv_state:
    language = check_group_exists(update, context)
    categories = bot_utils.get_categories(database, language)
    try:
        sent =  update.message.reply_text(
            text=bot_utils.get_text(database, language, 'category'),
            reply_markup=bot_utils.array_to_keyboard(categories)
        )
    
    except Exception:
        sent =  bot.send_message(
            text=bot_utils.get_text(database, language, 'category'),
            chat_id=update.effective_chat.id,
            reply_markup=bot_utils.array_to_keyboard(categories, selective=False)
        )

    ids.append(sent.message_id)
    return CATEGORY


def reply_to_category(update: Update, context: CallbackContext) -> conv_state:
    language = check_group_exists(update, context)
    category = update.message.text

    id = update.message.message_id
    ids.append(id)

    # Check category
    if category not in bot_utils.get_categories(database, language):
        sent =  update.message.reply_text(
                bot_utils.get_text(database, language, "keyboard")
            )
        ids.append(sent.message_id)

        ids.append(location_id)
        time.sleep(sleep)
        return end_conv_handler(update, context)

    tasks = bot_utils.get_tasks(database, category, language)
    
    sent =  update.message.reply_text(
        bot_utils.get_text(database, language,'task'),
        reply_markup=bot_utils.array_to_keyboard(tasks),
        parse_mode=parse_mode
    )
    ids.append(sent.message_id)
    return TASK


def save_task(update: Update, context: CallbackContext) -> conv_state:
    language = check_group_exists(update, context)
    text = update.message.text
    reward = text.split(",")[0]
    location_text = bot_utils.get_text(database, language, 'location')
    link = f"<a href='https://www.google.com/maps/search/?api=1&query={location.latitude},{location.longitude}'>{location_text if pokestop_name=='' else pokestop_name}</a>"

    
    id = update.message.message_id
    ids.append(id)

    if '/' not in text:
        reward = reward.split('✨')[0]
        # If unknown reward, cancel report
        if reward not in bot_utils.get_available_rewards(database, language):
            sent =  update.message.reply_text(
                bot_utils.get_text(database, language, "keyboard"),
                reply_markup=ReplyKeyboardRemove(selective=False)
            )
            ids.append(id)
            ids.append(location_id)
            ids.append(sent.message_id)
            time.sleep(sleep)
            return end_conv_handler(update, context)

        rows = text.split('\n')
        rows[0] = f"<b>{rows[0].split(',')[0]}</b>, <i>{','.join(rows[0].split(',')[1:])}</i>"
        text = '\n'.join(rows)
        
        text = f"{link}\n{text}\n{bot_utils.get_text(database, language, 'reported')} @{update.message.from_user.username}"
        bot_utils.save_task(
            database,
            update.effective_chat.id,
            update.message.message_id+1,
            update.message.from_user.id,
            location_id,
            location.longitude,
            location.latitude,
            reward, 
            pokestop_name
        )        
        markup = ReplyKeyboardRemove(selective=False)
    
    else: 
        # Split rewards
        rewards = reward.split('/')

        # Check they are correct
        for reward in rewards:
             if reward.split('✨')[0] not in bot_utils.get_available_rewards(database, language):
                sent = update.message.reply_text(
                    bot_utils.get_text(database, language, "keyboard"),
                    reply_markup=ReplyKeyboardRemove(selective=False)
                )
                ids.append(id)
                ids.append(location_id)
                ids.append(sent.message_id)
                time.sleep(sleep)
                return end_conv_handler(update, context)    
        
        # Save id to delete later
        bot_utils.save_unconfirmed(
            database,
            update.effective_chat.id,
            update.message.message_id+1,
            location_id
        )

        text = f"{link}\n<b>{bot_utils.get_text(database, language, 'unknown')}</b>,<i>{text.split(',')[1]}</i>\n{bot_utils.get_text(database, language, 'reported')} @{update.message.from_user.username}"
        keyboard = []
        for reward in rewards:
            button = InlineKeyboardButton(reward, callback_data=f"{reward},{location.longitude},{location.latitude},{pokestop_name},{location_id}")
            keyboard.append(button)
        markup = InlineKeyboardMarkup([keyboard])

        
    
    bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
        reply_markup=markup
    )

    return end_conv_handler(update, context)


def end_conv_handler(update: Update, context: CallbackContext) -> conv_state:
    global location, location_id, pokestop_name, ids
    with suppress(Exception):
        id = update.message.message_id
        ids.append(id)

    remove_messages(update, context, ids)
    location, location_id, pokestop_name, ids = [], 0, "", []
    return ConversationHandler.END


conversation_handler = ConversationHandler(
    entry_points=[
        MessageHandler(Filters.chat_type.groups & Filters.location, telegram_location),
        MessageHandler(Filters.chat_type.groups & Filters.regex(r'[+-]?[0-9]+(\.[0-9]+)?,[ ]?[+-]?[0-9]+(\.[0-9]+)?'), coords_location)
    ],

    states={
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler)
        ],
        CATEGORY: [	
            MessageHandler(Filters.text, reply_to_category)
        ],

        POKESTOP: [	
            MessageHandler(Filters.text, reply_to_pokestop)
        ],

        TASK: [
            MessageHandler(Filters.text, save_task)
        ]
    },

    fallbacks=[	
        MessageHandler(Filters.regex('Cancel'), end_conv_handler)
    ]
)


def main():   
    # Clear 
    dp.add_handler(MessageHandler(Filters.chat_type.private & Filters.regex(r"^/delete_timezone"), delete_timezone))   
    dp.add_handler(MessageHandler(Filters.chat_type.private & Filters.regex(r"^/delete_event"), delete_event))    
    
    # Any chat
    dp.add_handler(MessageHandler(Filters.regex("^/help"), help))
    dp.add_handler(CommandHandler("get_timezones", get_timezones))
    dp.add_handler(conversation_handler)
    dp.add_handler(CallbackQueryHandler(inline_keyboard_handler))

    # Only in group
    dp.add_handler(MessageHandler(Filters.chat_type.groups & Filters.regex (r"^/delete$"), delete_report))
    dp.add_handler(MessageHandler(Filters.chat_type.groups & Filters.regex(r"^/add_group"), add_group))
    dp.add_handler(MessageHandler(Filters.chat_type.groups & Filters.regex(r"^/get"), get_reports))

    # Only in private 
    dp.add_handler(MessageHandler(Filters.chat_type.private & Filters.regex(r"^/start"), start))    
    dp.add_handler(MessageHandler(Filters.chat_type.private & Filters.regex(r"^/set_lang"), set_lang_command))
    dp.add_handler(MessageHandler(Filters.chat_type.private & Filters.regex(r"^/rewards"), get_rewards))
    dp.add_handler(MessageHandler(Filters.chat_type.private, default_private_handler))

    dp.add_error_handler(error_callback)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
