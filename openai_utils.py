from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

def call_openai_api(prompt, model='gpt-4o'):
    """OpenAI API를 직접 호출하는 함수"""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content

    
    # full_response = ""
    # for chunk in stream:
    #     if chunk.choices[0].delta.content:
    #         content = chunk.choices[0].delta.content
    #         print(content, end="", flush=True)
    #         full_response += content
    
    # print()  # 줄바꿈 추가
    # return full_response