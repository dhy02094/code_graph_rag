import json
from neo4j import GraphDatabase
import os

class JavaProjectGraphLoader:
    def __init__(self, uri, username, password, database="neo4j"):
        """Neo4j 연결 설정"""
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
        
    def close(self):
        """연결 종료"""
        self.driver.close()
        
    def load_project(self, json_file_path):
        """JSON 파일에서 프로젝트 구조를 로드하고 GraphDB에 적재"""
        # JSON 파일 로드
        with open(json_file_path, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
        
        # 데이터베이스 초기화 (이전 데이터 삭제)
        self._clear_database()
        
        # 프로젝트 루트 노드 생성
        project_path = project_data['project_path']
        project_name = os.path.basename(project_path)
        self._create_project(project_name, project_path)
        
        # 패키지 노드 생성 및 관계 설정
        packages = set()
        for file_path, file_info in project_data['files'].items():
            if 'error' in file_info:
                continue
                
            package = file_info.get('package')
            if package:
                packages.add(package)
                self._create_package(package)
        
        # 패키지 계층 구조 생성
        self._create_package_hierarchy(packages)
        
        # 파일, 클래스, 인터페이스 노드 생성 및 관계 설정
        for file_path, file_info in project_data['files'].items():
            if 'error' in file_info:
                continue
                
            package = file_info.get('package')
            file_name = os.path.basename(file_path)
            
            # 파일 노드 생성
            self._create_file(file_name, file_path, package)
            
            # 클래스 노드 생성
            for class_info in file_info.get('classes', []):
                class_name = class_info['name']
                full_class_name = f"{package}.{class_name}" if package else class_name
                extends = class_info.get('extends')
                
                self._create_class(class_name, full_class_name, package, file_path)
                
                # 메서드 노드 생성
                for method_info in class_info.get('methods', []):
                    method_name = method_info['name']
                    return_type = method_info.get('return_type')
                    
                    self._create_method(method_name, return_type, full_class_name)
                
                # 상속 관계 설정
                if extends:
                    self._create_extends_relationship(full_class_name, extends)
                
                # 구현 관계 설정
                for interface in class_info.get('implements', []):
                    self._create_implements_relationship(full_class_name, interface)
            
            # 인터페이스 노드 생성
            for interface_info in file_info.get('interfaces', []):
                interface_name = interface_info['name']
                full_interface_name = f"{package}.{interface_name}" if package else interface_name
                extends = interface_info.get('extends', [])
                
                self._create_interface(interface_name, full_interface_name, package, file_path)
                
                # 메서드 노드 생성
                for method_info in interface_info.get('methods', []):
                    method_name = method_info['name']
                    return_type = method_info.get('return_type')
                    
                    self._create_method(method_name, return_type, full_interface_name)
                
                # 인터페이스 확장 관계 설정
                for ext in extends:
                    self._create_extends_relationship(full_interface_name, ext)
        
        # 임포트 관계 설정
        for file_path, file_info in project_data['files'].items():
            if 'error' in file_info:
                continue
                
            package = file_info.get('package')
            file_name = os.path.basename(file_path)
            
            # 임포트 관계 설정
            for dependency in file_info.get('dependencies', []):
                if dependency['type'] == 'import':
                    self._create_import_relationship(file_path, dependency['target'])
    
    def _execute_query(self, query, parameters=None):
        """Cypher 쿼리 실행"""
        with self.driver.session(database=self.database) as session:
            result = session.run(query, parameters)
            return list(result)
    
    def _clear_database(self):
        """데이터베이스 초기화"""
        query = "MATCH (n) DETACH DELETE n"
        self._execute_query(query)
        print("데이터베이스를 초기화했습니다.")
    
    def _create_project(self, project_name, project_path):
        """프로젝트 노드 생성"""
        query = """
        CREATE (p:Project {
            name: $name,
            path: $path
        })
        """
        self._execute_query(query, {"name": project_name, "path": project_path})
        print(f"프로젝트 노드를 생성했습니다: {project_name}")
    
    def _create_package(self, package_name):
        """패키지 노드 생성"""
        query = """
        MERGE (p:Package {
            name: $name
        })
        """
        self._execute_query(query, {"name": package_name})
        print(f"패키지 노드를 생성했습니다: {package_name}")
    
    def _create_package_hierarchy(self, packages):
        """패키지 계층 구조 생성"""
        package_hierarchy = {}
        
        # 모든 패키지를 정렬하여 처리 (상위 패키지가 먼저 생성되도록)
        sorted_packages = sorted(packages)
        
        for package in sorted_packages:
            parts = package.split('.')
            
            # 상위 패키지 찾기
            for i in range(1, len(parts)):
                parent_package = '.'.join(parts[:i])
                child_package = '.'.join(parts[:i+1])
                
                if parent_package and child_package:
                    query = """
                    MATCH (parent:Package {name: $parent_name})
                    MATCH (child:Package {name: $child_name})
                    MERGE (parent)-[:CONTAINS]->(child)
                    """
                    self._execute_query(query, {"parent_name": parent_package, "child_name": child_package})
        
        print("패키지 계층 구조를 생성했습니다.")
    
    def _create_file(self, file_name, file_path, package_name):
        """파일 노드 생성"""
        query = """
        MERGE (f:File {
            name: $name,
            path: $path
        })
        """
        self._execute_query(query, {"name": file_name, "path": file_path})
        
        if package_name:
            query = """
            MATCH (p:Package {name: $package_name})
            MATCH (f:File {path: $file_path})
            MERGE (p)-[:CONTAINS]->(f)
            """
            self._execute_query(query, {"package_name": package_name, "file_path": file_path})
        
        print(f"파일 노드를 생성했습니다: {file_name}")
    
    def _create_class(self, class_name, full_class_name, package_name, file_path):
        """클래스 노드 생성"""
        query = """
        MERGE (c:Class {
            name: $name,
            fullName: $full_name
        })
        """
        self._execute_query(query, {"name": class_name, "full_name": full_class_name})
        
        # 패키지-클래스 관계 설정
        if package_name:
            query = """
            MATCH (p:Package {name: $package_name})
            MATCH (c:Class {fullName: $full_class_name})
            MERGE (p)-[:CONTAINS]->(c)
            """
            self._execute_query(query, {"package_name": package_name, "full_class_name": full_class_name})
        
        # 파일-클래스 관계 설정
        query = """
        MATCH (f:File {path: $file_path})
        MATCH (c:Class {fullName: $full_class_name})
        MERGE (f)-[:CONTAINS]->(c)
        """
        self._execute_query(query, {"file_path": file_path, "full_class_name": full_class_name})
        
        print(f"클래스 노드를 생성했습니다: {full_class_name}")
    
    def _create_interface(self, interface_name, full_interface_name, package_name, file_path):
        """인터페이스 노드 생성"""
        query = """
        MERGE (i:Interface {
            name: $name,
            fullName: $full_name
        })
        """
        self._execute_query(query, {"name": interface_name, "full_name": full_interface_name})
        
        # 패키지-인터페이스 관계 설정
        if package_name:
            query = """
            MATCH (p:Package {name: $package_name})
            MATCH (i:Interface {fullName: $full_interface_name})
            MERGE (p)-[:CONTAINS]->(i)
            """
            self._execute_query(query, {"package_name": package_name, "full_interface_name": full_interface_name})
        
        # 파일-인터페이스 관계 설정
        query = """
        MATCH (f:File {path: $file_path})
        MATCH (i:Interface {fullName: $full_interface_name})
        MERGE (f)-[:CONTAINS]->(i)
        """
        self._execute_query(query, {"file_path": file_path, "full_interface_name": full_interface_name})
        
        print(f"인터페이스 노드를 생성했습니다: {full_interface_name}")
    
    def _create_method(self, method_name, return_type, parent_full_name):
        """메서드 노드 생성"""
        method_id = f"{parent_full_name}.{method_name}"

        # return_type이 null이면 기본값 설정
        if return_type is None:
            return_type = "void"  # 또는 빈 문자열 ""

        query = """
        MERGE (m:Method {
            name: $name,
            id: $id,
            returnType: $return_type
        })
        """
        self._execute_query(query, {"name": method_name, "id": method_id, "return_type": return_type})
        
        # 클래스/인터페이스-메서드 관계 설정
        query = """
        MATCH (c {fullName: $parent_full_name})
        MATCH (m:Method {id: $method_id})
        MERGE (c)-[:DECLARES]->(m)
        """
        self._execute_query(query, {"parent_full_name": parent_full_name, "method_id": method_id})
        
        print(f"메서드 노드를 생성했습니다: {method_id}")
    
    def _create_extends_relationship(self, child_full_name, parent_name):
        """상속 관계 설정"""
        # 부모 클래스의 fullName은 모를 수 있으므로 name으로 검색
        query = """
        MATCH (child {fullName: $child_full_name})
        MATCH (parent {name: $parent_name})
        MERGE (child)-[:EXTENDS]->(parent)
        """
        self._execute_query(query, {"child_full_name": child_full_name, "parent_name": parent_name})
        print(f"상속 관계를 설정했습니다: {child_full_name} -> {parent_name}")
    
    def _create_implements_relationship(self, class_full_name, interface_name):
        """구현 관계 설정"""
        query = """
        MATCH (c:Class {fullName: $class_full_name})
        MATCH (i:Interface {name: $interface_name})
        MERGE (c)-[:IMPLEMENTS]->(i)
        """
        self._execute_query(query, {"class_full_name": class_full_name, "interface_name": interface_name})
        print(f"구현 관계를 설정했습니다: {class_full_name} -> {interface_name}")
    
    def _create_import_relationship(self, file_path, import_target):
        """임포트 관계 설정"""
        query = """
        MATCH (f:File {path: $file_path})
        MERGE (i:Import {name: $import_target})
        MERGE (f)-[:IMPORTS]->(i)
        """
        self._execute_query(query, {"file_path": file_path, "import_target": import_target})
        print(f"임포트 관계를 설정했습니다: {file_path} -> {import_target}")

if __name__ == "__main__":
    # 사용 예시
    # uri = "bolt://localhost:7687"  # Neo4j 서버 주소
    uri = "neo4j+s://bc50b223.databases.neo4j.io"
    username = "neo4j"             # 기본 사용자 이름
    password = "0mTKomu9ETlWt7JctP2hiPT7FnPfsW7gjV5EFBO6wvI"          # 비밀번호 변경 필요
    
    loader = JavaProjectGraphLoader(uri, username, password)
    
    try:
        # JSON 파일 경로
        json_file_path = "tmp.json"
        loader.load_project(json_file_path)
        print("프로젝트가 성공적으로 Neo4j에 로드되었습니다.")
    finally:
        loader.close()