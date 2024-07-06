import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
from langchain.chat_models import ChatOpenAI

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

@app.event("app_mention")
def handle_mention(event, say):
    thread_ts = event["ts"]
    message = re.sub("<@.*>","",event["text"])

    llm = ChatOpenAI(
        model_name=os.environ["OPENAI_API_MODEL"],
        temperature=os.environ["OPENAI_TEMPERATURE"],
    )

    response = llm.predict(message)
    say(thread_ts=thread_ts,text=response)

if __name__ == "__main__" :
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()