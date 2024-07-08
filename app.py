import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
from langchain.chat_models import ChatOpenAI
import time
from typing import Any
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import LLMResult
from datetime import timedelta
from langchain.memory import MomentoChatMessageHistory
from langchain.schema import HumanMessage, LLMResult, SystemMessage
import json
import logging
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

CHAT_UPDATE_INTERVAL_SEC = 1

load_dotenv()

# ログ
SlackRequestHandler.clear_all_log_handlers()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

app = App(
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    token=os.environ["SLACK_BOT_TOKEN"],
    process_before_response=True,
)

class SlackStreamingCallbackHandler(BaseCallbackHandler):
    last_send_time = time.time()
    message = ""

    def __init__(self, channel, ts):
        self.channel = channel
        self.ts = ts
        self.interval = CHAT_UPDATE_INTERVAL_SEC
        self.update_count = 0
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.message += token

        now = time.time()
        if now - self.last_send_time > CHAT_UPDATE_INTERVAL_SEC:
            self.last_send_time = now
            app.client.chat_update(
                channel=self.channel, ts=self.ts, text=f"{self.message}..."
            )
            self.last_send_time = now
            self.update_count += 1

            if self.update_count / 10 > self.interval:
                self.interval = self.interval * 2
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any)->Any:
        app.client.chat_update(channel=self.channel, ts=self.ts, text=self.message)

def handle_mention(event, say):
    channel = event["channel"]
    thread_ts = event["ts"]
    message = re.sub("<@.*>","",event["text"])

    id_ts = event["ts"]
    if "thread_ts" in event:
        id_ts = event["thread_ts"]

    result = say("\n\nTyping...",thread_ts=thread_ts)
    ts = result["ts"]

    history = MomentoChatMessageHistory.from_client_params(
        id_ts,
        os.environ["MOMENTO_CACHE"],
        timedelta(hours=int(os.environ["MOMENTO_TTL"])),
    )

    messages = [SystemMessage(content="You are agood assistant.")]
    messages.extend(history.messages)
    messages.append(HumanMessage(content=message))

    history.add_user_message(message)

    callback = SlackStreamingCallbackHandler(channel=channel,ts=ts)
    llm = ChatOpenAI(
        model_name=os.environ["OPENAI_API_MODEL"],
        temperature=os.environ["OPENAI_TEMPERATURE"],
        streaming=True,
        callbacks=[callback],
    )

    ai_message = llm(messages)
    history.add_message(ai_message)

def just_ack(ack):
    ack()

app.event("app_mention")(ack=just_ack, lazy=[handle_mention])

if __name__ == "__main__" :
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()

def handler(event, context):
    logging.info("handler called")
    header = event["headers"]
    logger.info(json.dumps(header))

    if "x-slack-retry-num" in header:
        logger.info("SKIP > x-slack-retry-num: %s", header["x-slack-retry-num"])
        return 200

    slack_handler = SlackRequestHandler(app=app)
    return slack_handler.handle(event, context)