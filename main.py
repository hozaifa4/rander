import os
import logging
from dotenv import load_dotenv
from telethon.sync import TelegramClient, events
import asyncio # asyncio ইম্পোর্ট করা হয়েছে

# .env ফাইল থেকে এনভায়রনমেন্ট ভেরিয়েবল লোড করা
load_dotenv()

# লগার কনফিগার করা (সমস্যা নির্ণয়ে সাহায্য করবে)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s/%(asctime)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# এনভায়রনমেন্ট ভेरিয়েবল থেকে মানগুলো নেওয়া
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE_NUMBER')
SESSION_NAME = os.getenv('TELEGRAM_SESSION_NAME', 'my_telegram_bot_session') # ডিফল্ট সেশন নাম

SOURCE_CHANNEL_ID_STR = os.getenv('SOURCE_CHANNEL_ID')
DESTINATION_CHANNEL_ID_STR = os.getenv('DESTINATION_CHANNEL_ID')
# KEYWORDS_STR = os.getenv('KEYWORDS_TO_FILTER', "buy,sell") # এই লাইনটি এখন আর ব্যবহৃত হচ্ছে না

# ভেরিয়েবলগুলো ঠিকভাবে লোড হয়েছে কিনা তা পরীক্ষা করা
if not all([API_ID, API_HASH, PHONE_NUMBER]):
    logger.critical("Error: Missing critical environment variables (API_ID, API_HASH, PHONE_NUMBER). Please check your .env file or environment settings.")
    exit()

try:
    API_ID = int(API_ID)
except ValueError:
    logger.critical("Error: TELEGRAM_API_ID in .env file is not a valid integer.")
    exit()

# চ্যানেল আইডি ও কিওয়ার্ডগুলোকে প্রসেস করা
try:
    SOURCE_CHANNEL_ID = int(SOURCE_CHANNEL_ID_STR) if SOURCE_CHANNEL_ID_STR else None
    DESTINATION_CHANNEL_ID = int(DESTINATION_CHANNEL_ID_STR) if DESTINATION_CHANNEL_ID_STR else None
except ValueError:
    logger.warning("Warning: SOURCE_CHANNEL_ID or DESTINATION_CHANNEL_ID is not a valid integer. Message forwarding will be disabled until valid IDs are provided.")
    SOURCE_CHANNEL_ID = None
    DESTINATION_CHANNEL_ID = None

# KEYWORDS_TO_FILTER = [keyword.strip().lower() for keyword in KEYWORDS_STR.split(',')] # এই লাইনটিও এখন আর ব্যবহৃত হচ্ছে না

# টেলিগ্রাম ক্লায়েন্ট তৈরি করা
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def main():
    logger.info("Connecting to Telegram...")
    try:
        # ক্লায়েন্ট কানেক্ট ও অথোরাইজ করা
        await client.connect()
        if not await client.is_user_authorized():
            logger.info(f"First time login or session expired. Sending code request to {PHONE_NUMBER}...")
            await client.send_code_request(PHONE_NUMBER)
            try:
                await client.sign_in(PHONE_NUMBER, input('Enter the code you received: '))
                logger.info("Signed in successfully!")
            except Exception as e:
                logger.error(f"Failed to sign in: {e}")
                return
        else:
            logger.info("Already authorized.")

        me = await client.get_me()
        logger.info(f"Working with account: {me.first_name} (ID: {me.id})")

        if not SOURCE_CHANNEL_ID or not DESTINATION_CHANNEL_ID:
            logger.warning("Source or Destination Channel ID is not set. Message processing will not start.")
            logger.info("To find channel IDs, you can send a message from the channel to a bot like @JsonDumpBot or @ShowJsonBot, then look for 'chat_id' or 'sender_chat'. Alternatively, forward a message from the channel to your own account and use `client.get_dialogs()` (see Telethon docs for examples).")
            return

        logger.info(f"Listening for new messages in Source Channel: {SOURCE_CHANNEL_ID}")
        logger.info(f"Forwarding matched messages to Destination Channel: {DESTINATION_CHANNEL_ID}")
        # logger.info(f"Filtering for keywords: {KEYWORDS_TO_FILTER}") # এই লগ মেসেজটি এখন আর প্রাসঙ্গিক নয়

        # নতুন মেসেজের জন্য ইভেন্ট হ্যান্ডলার
        @client.on(events.NewMessage(chats=SOURCE_CHANNEL_ID))
        async def handle_new_message(event):
            message = event.message
            
            if not message.text:
                logger.info(f"Message ID {message.id} has no text content. Skipped.")
                return

            logger.info(f"New message received (ID: {message.id}): '{message.text[:50]}...'")

            message_text_original = message.text
            message_text_lower = message_text_original.lower()

            # নতুন লজিক অনুযায়ী শর্তগুলো পরীক্ষা করা
            contains_listed = "listed" in message_text_lower
            contains_spot = "spot" in message_text_lower
            
            dollar_prefixed_word_found = None
            token_to_show = None # $ চিহ্নের পরের অংশ

            if contains_listed and contains_spot:
                logger.info(f"Message ID {message.id}: Contains 'listed' and 'spot'. Looking for '$'-prefixed token...")
                words_in_message = message_text_original.split()
                for word in words_in_message:
                    if word.startswith('$') and len(word) > 1: # যেমন $BTC, শুধু $ নয়
                        dollar_prefixed_word_found = word
                        token_to_show = word[1:] # '$' চিহ্নের পরের অংশটুকু নেওয়া
                        logger.info(f"Message ID {message.id}: '$'-prefixed word '{dollar_prefixed_word_found}' found. Token: '{token_to_show}'.")
                        break 
                
                if token_to_show:
                    # সব শর্ত পূরণ হলে মেসেজ পাঠানো হবে
                    output_message = f"buy {token_to_show}" # আউটপুট ফরম্যাট: "buy TOKEN"
                    
                    try:
                        await client.send_message(DESTINATION_CHANNEL_ID, output_message, link_preview=False)
                        logger.info(f"SENT: '{output_message}' to destination channel (from original message ID {message.id})")
                    except Exception as e:
                        logger.error(f"Error sending message to destination channel: {e}")
                else:
                    logger.info(f"Message ID {message.id}: Contains 'listed' and 'spot', but no valid '$-prefixed' token found. Skipped.")
            else:
                # কোন শর্ত পূরণ হয়নি তা লগ করা
                skip_reasons = []
                if not contains_listed:
                    skip_reasons.append("'listed' not found")
                if not contains_spot:
                    skip_reasons.append("'spot' not found")
                logger.info(f"Message ID {message.id}: Skipped. Reason(s): {', '.join(skip_reasons)}.")

        logger.info("Bot is running and waiting for messages...")
        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if client.is_connected(): # client.is_connected() ব্যবহার করা উচিত
            logger.info("Disconnecting client...")
            await client.disconnect()
        logger.info("Program finished.")

if __name__ == '__main__':
    # asyncio.run(main()) আগের কোডে ছিল, এটি সরাসরি Telethon v1 (sync) এর সাথে কাজ করে
    # যদি Telethon v1 (sync) client ব্যবহার করা হয়, তাহলে client.loop.run_until_complete(main()) অথবা সরাসরি client.start(); client.run_until_disconnected() ব্যবহার করা হয়।
    # প্রদত্ত কোডটিতে Telethon sync ক্লায়েন্ট ব্যবহার করা হলেও main ফাংশনটি async হিসেবে ডিফাইন করা হয়েছে 
    # এবং asyncio.run(main()) দিয়ে চালানো হচ্ছে, যা সঠিক।

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program stopped by user (Ctrl+C).")
