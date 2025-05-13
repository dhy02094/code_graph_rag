import os
from neo4j import GraphDatabase
import openai
from dotenv import load_dotenv
import re

# 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 설정
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class CodeAssistant:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password):
        # Neo4j 연결
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        
    def close(self):
        self.driver.close()
        
    def run_query(self, query):
        with self.driver.session() as session:
            result = session.run(query)
            return [record.data() for record in result]
    
    def ask(self, question):
        # 1. 질문을 Cypher 쿼리로 변환
        cypher_query = self.generate_cypher_query(question)
        print(f"🔍 생성된 쿼리: {cypher_query}")
        
        try:
            # 2. 쿼리 실행
            results = self.run_query(cypher_query)
            print(f"✅ 쿼리 실행 완료 (결과 {len(results)}개)")
            
            # 3. 결과 해석
            answer = self.interpret_results(question, cypher_query, results)
            return answer
            
        except Exception as e:
            error_msg = f"❌ 오류 발생: {str(e)}"
            print(error_msg)
            return f"죄송합니다. 쿼리 실행 중 오류가 발생했습니다: {str(e)}"
    
    def generate_cypher_query(self, question):
        prompt = f"""
        당신은 Java 코드 구조가 저장된 Neo4j 데이터베이스를 위한 Cypher 쿼리 생성 전문가입니다.
        
        데이터 모델:
        노드: Project, Package, File, Class, Interface, Method, Import
        관계: CONTAINS, EXTENDS, IMPLEMENTS, IMPORTS, DECLARES
        
        다음 질문에 대한 Cypher 쿼리를 작성해주세요.
        질문: {question}
        
        쿼리만 출력하세요. 마크다운 코드 블록(```)이나 설명, 주석을 포함하지 마세요.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
            
        raw_query = response.choices[0].message.content.strip()
    
        # 정규식을 사용하여 마크다운 코드 블록 제거
        # ```로 시작하고 ```로 끝나는 패턴 제거
        clean_query = re.sub(r'^```[\w\s]*\n(.*?)\n```$', r'\1', raw_query, flags=re.DOTALL)
        
        # 혹시 남아있는 ```를 제거
        clean_query = clean_query.replace('```', '')
        
        # 시작과 끝의 공백 제거
        clean_query = clean_query.strip()
        
        print(f"원본 쿼리: {raw_query}")
        print(f"정제된 쿼리: {clean_query}")
        
        return clean_query
    
    def interpret_results(self, question, query, results):
        prompt = f"""
        질문: {question}
        
        실행된 Cypher 쿼리: {query}
        
        데이터베이스 결과: {results}
        
        위 정보를 바탕으로 질문에 대한 명확한 답변을 제공해주세요.
        결과가 없다면 '해당 정보를 찾을 수 없습니다'라고 답변해주세요.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        return response.choices[0].message.content

# 실행 코드
if __name__ == "__main__":
    # Neo4j 연결 정보
    uri = "neo4j+s://bc50b223.databases.neo4j.io"  # 실제 URI로 변경
    username = "neo4j"
    password = "0mTKomu9ETlWt7JctP2hiPT7FnPfsW7gjV5EFBO6wvI"  # 실제 비밀번호로 변경
    
    # 어시스턴트 인스턴스 생성
    assistant = CodeAssistant(uri, username, password)
    
    try:
        print("💻 Java 코드 분석 어시스턴트가 준비되었습니다. 종료하려면 'exit' 또는 'quit'을 입력하세요.")
        
        while True:
            # 사용자 입력 받기
            question = input("\n질문: ")
            
            # 종료 명령 확인
            if question.lower() in ["exit", "quit", "종료"]:
                print("프로그램을 종료합니다. 감사합니다!")
                break
            
            # 질문 처리 및 답변
            answer = assistant.ask(question)
            print("\n답변:")
            print(answer)
            print("\n" + "-"*50)
            
    finally:
        # 연결 종료
        assistant.close()