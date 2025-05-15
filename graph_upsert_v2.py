import json
from neo4j import GraphDatabase
import os

class CodeAnalyzerGraphLoader:
    def __init__(self, uri, username, password, database="neo4j"):
        """Neo4j 연결 설정"""
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
        
    def close(self):
        """연결 종료"""
        self.driver.close()
        
    def load_project(self, json_file_path):
        """JSON 파일에서 AST 데이터를 로드하고 GraphDB에 적재"""
        # JSON 파일 로드
        with open(json_file_path, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
        
        # 데이터베이스 초기화 (이전 데이터 삭제)
        self._clear_database()
        
        # 프로젝트 루트 노드 생성
        project_path = project_data['project_path']
        project_name = os.path.basename(project_path)
        self._create_project(project_name, project_path)
        
        # 패키지 노드 생성
        packages = set()
        for file_path, file_info in project_data['files'].items():
            package = file_info.get('package')
            if package:
                packages.add(package)
                self._create_package(package)
        
        # 패키지 계층 구조 생성
        self._create_package_hierarchy(packages)
        
        # 파일 노드 생성
        for file_path, file_info in project_data['files'].items():
            package = file_info.get('package')
            file_name = os.path.basename(file_path)
            
            # 파일 노드 생성
            self._create_file(file_name, file_path, package)
            
            # 임포트 노드 생성
            for import_stmt in file_info.get('imports', []):
                self._create_import(import_stmt)
                self._create_file_imports_relationship(file_path, import_stmt)
            
            # 클래스 노드 생성
            for class_info in file_info.get('classes', []):
                class_name = class_info['name']
                full_class_name = f"{package}.{class_name}" if package else class_name
                extends = class_info.get('extends')
                
                # 클래스 속성
                properties = {
                    "name": class_name,
                    "fullName": full_class_name,
                    "extends": extends if extends else ""
                }
                
                self._create_class(properties, package, file_path)
                
                # 필드 노드 생성
                for field_info in class_info.get('fields', []):
                    field_name = field_info['name']
                    field_type = field_info.get('type', '')
                    
                    field_properties = {
                        "name": field_name,
                        "type": field_type,
                        "class_name": full_class_name
                    }
                    
                    self._create_field(field_properties, full_class_name)
                
                # 메서드 노드 생성
                for method_info in class_info.get('methods', []):
                    method_name = method_info['name']
                    return_type = method_info.get('return_type', 'void')
                    documentation = method_info.get('documentation', '')
                    description = method_info.get('description', '')
                    body = method_info.get('body', '')
                    
                    method_properties = {
                        "name": method_name,
                        "returnType": return_type if return_type else "void",
                        "documentation": documentation if documentation else "",  # NULL 방지
                        "description": description if description else "",       # NULL 방지
                        "body": body if body else "",                           # NULL 방지
                        "parent_name": full_class_name
                    }
                    
                    method_id = self._create_method(method_properties)
                    
                    # 파라미터 노드 생성
                    for param_info in method_info.get('parameters', []):
                        param_name = param_info['name']
                        param_type = param_info.get('type', '')
                        
                        param_properties = {
                            "name": param_name,
                            "type": param_type if param_type else "",
                            "method_id": method_id
                        }
                        
                        self._create_parameter(param_properties, method_id)
                
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
                
                # 인터페이스 속성
                properties = {
                    "name": interface_name,
                    "fullName": full_interface_name
                }
                
                self._create_interface(properties, package, file_path)
                
                # 메서드 노드 생성
                for method_info in interface_info.get('methods', []):
                    method_name = method_info['name']
                    return_type = method_info.get('return_type', '')
                    description = method_info.get('description', '')
                    documentation = method_info.get('documentation', '')
                    body = method_info.get('body', '')
                    
                    method_properties = {
                        "name": method_name,
                        "returnType": return_type if return_type else "void",
                        "documentation": documentation if documentation else "",  # NULL 방지
                        "description": description if description else "",        # NULL 방지
                        "body": body if body else "",                            # NULL 방지
                        "parent_name": full_interface_name
                    }
                    
                    method_id = self._create_method(method_properties)
                    
                    # 파라미터 노드 생성
                    for param_info in method_info.get('parameters', []):
                        param_name = param_info['name']
                        param_type = param_info.get('type', '')
                        
                        param_properties = {
                            "name": param_name,
                            "type": param_type if param_type else "",
                            "method_id": method_id
                        }
                        
                        self._create_parameter(param_properties, method_id)
                
                # 인터페이스 확장 관계 설정
                for ext in extends:
                    self._create_extends_relationship(full_interface_name, ext)
        
        # 의존성 관계 설정
        for file_path, file_info in project_data['files'].items():
            for dependency in file_info.get('dependencies', []):
                if dependency.get('type') == 'import' and dependency.get('file'):
                    self._create_file_depends_on_relationship(file_path, dependency['file'])
        
        print("모든 데이터가 Neo4j에 로드되었습니다.")
    
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
        sorted_packages = sorted(packages)
        
        for package in sorted_packages:
            parts = package.split('.')
            
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
        
        # 프로젝트-파일 관계 설정
        query = """
        MATCH (p:Project)
        MATCH (f:File {path: $file_path})
        MERGE (p)-[:CONTAINS]->(f)
        """
        self._execute_query(query, {"file_path": file_path})
        
        print(f"파일 노드를 생성했습니다: {file_name}")
    
    def _create_import(self, import_name):
        """임포트 노드 생성"""
        query = """
        MERGE (i:Import {
            name: $name
        })
        """
        self._execute_query(query, {"name": import_name})
    
    def _create_file_imports_relationship(self, file_path, import_name):
        """파일-임포트 관계 설정"""
        query = """
        MATCH (f:File {path: $file_path})
        MATCH (i:Import {name: $import_name})
        MERGE (f)-[:IMPORTS]->(i)
        """
        self._execute_query(query, {"file_path": file_path, "import_name": import_name})
    
    def _create_class(self, properties, package_name, file_path):
        """클래스 노드 생성"""
        query = """
        MERGE (c:Class {
            name: $name,
            fullName: $fullName,
            extends: $extends
        })
        """
        self._execute_query(query, properties)
        
        # 패키지-클래스 관계 설정
        if package_name:
            query = """
            MATCH (p:Package {name: $package_name})
            MATCH (c:Class {fullName: $full_class_name})
            MERGE (p)-[:CONTAINS]->(c)
            """
            self._execute_query(query, {"package_name": package_name, "full_class_name": properties["fullName"]})
        
        # 파일-클래스 관계 설정
        query = """
        MATCH (f:File {path: $file_path})
        MATCH (c:Class {fullName: $full_class_name})
        MERGE (f)-[:CONTAINS]->(c)
        """
        self._execute_query(query, {"file_path": file_path, "full_class_name": properties["fullName"]})
        
        print(f"클래스 노드를 생성했습니다: {properties['fullName']}")
    
    def _create_field(self, properties, class_full_name):
        """필드 노드 생성"""
        field_id = f"{class_full_name}.{properties['name']}"
        
        query = """
        MERGE (f:Field {
            name: $name,
            type: $type,
            id: $id,
            class_name: $class_name
        })
        """
        self._execute_query(query, {"name": properties["name"], "type": properties["type"], 
                                    "id": field_id, "class_name": class_full_name})
        
        # 클래스-필드 관계 설정
        query = """
        MATCH (c:Class {fullName: $class_full_name})
        MATCH (f:Field {id: $field_id})
        MERGE (c)-[:HAS_FIELD]->(f)
        """
        self._execute_query(query, {"class_full_name": class_full_name, "field_id": field_id})
        
        print(f"필드 노드를 생성했습니다: {field_id}")
    
    def _create_interface(self, properties, package_name, file_path):
        """인터페이스 노드 생성"""
        query = """
        MERGE (i:Interface {
            name: $name,
            fullName: $fullName
        })
        """
        self._execute_query(query, properties)
        
        # 패키지-인터페이스 관계 설정
        if package_name:
            query = """
            MATCH (p:Package {name: $package_name})
            MATCH (i:Interface {fullName: $full_interface_name})
            MERGE (p)-[:CONTAINS]->(i)
            """
            self._execute_query(query, {"package_name": package_name, "full_interface_name": properties["fullName"]})
        
        # 파일-인터페이스 관계 설정
        query = """
        MATCH (f:File {path: $file_path})
        MATCH (i:Interface {fullName: $full_interface_name})
        MERGE (f)-[:CONTAINS]->(i)
        """
        self._execute_query(query, {"file_path": file_path, "full_interface_name": properties["fullName"]})
        
        print(f"인터페이스 노드를 생성했습니다: {properties['fullName']}")
    
    def _create_method(self, properties):
        """메서드 노드 생성"""
        method_id = f"{properties['parent_name']}.{properties['name']}"
        
        query = """
        MERGE (m:Method {
            name: $name,
            id: $id,
            returnType: $returnType,
            documentation: $documentation,
            description: $description,
            body: $body,
            parent_name: $parent_name
        })
        """
        params = {
            "name": properties["name"],
            "id": method_id,
            "returnType": properties["returnType"],
            "documentation": properties["documentation"],
            "description": properties["description"],
            "body": properties["body"],
            "parent_name": properties["parent_name"]
        }
        self._execute_query(query, params)
        
        # 클래스/인터페이스-메서드 관계 설정
        query = """
        MATCH (c {fullName: $parent_full_name})
        MATCH (m:Method {id: $method_id})
        MERGE (c)-[:DECLARES]->(m)
        """
        self._execute_query(query, {"parent_full_name": properties["parent_name"], "method_id": method_id})
        
        print(f"메서드 노드를 생성했습니다: {method_id}")
        return method_id
    
    def _create_parameter(self, properties, method_id):
        """파라미터 노드 생성"""
        param_id = f"{method_id}.{properties['name']}"
        
        query = """
        MERGE (p:Parameter {
            name: $name,
            type: $type,
            id: $id,
            method_id: $method_id
        })
        """
        self._execute_query(query, {"name": properties["name"], "type": properties["type"], 
                                    "id": param_id, "method_id": method_id})
        
        # 메서드-파라미터 관계 설정
        query = """
        MATCH (m:Method {id: $method_id})
        MATCH (p:Parameter {id: $param_id})
        MERGE (m)-[:HAS_PARAMETER]->(p)
        """
        self._execute_query(query, {"method_id": method_id, "param_id": param_id})
        
        print(f"파라미터 노드를 생성했습니다: {param_id}")
    
    def _create_extends_relationship(self, child_full_name, parent_name):
        """상속 관계 설정"""
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
    
    def _create_file_depends_on_relationship(self, source_file, target_file):
        """파일 의존성 관계 설정"""
        query = """
        MATCH (source:File {path: $source_file})
        MATCH (target:File {path: $target_file})
        MERGE (source)-[:DEPENDS_ON]->(target)
        """
        self._execute_query(query, {"source_file": source_file, "target_file": target_file})
        print(f"파일 의존성 관계를 설정했습니다: {source_file} -> {target_file}")

    def find_related_method_nodes(self, method_name):
        """특정 메서드와 연관된 노드 찾기"""
        query = """
        MATCH (m:Method {name: $method_name})
        OPTIONAL MATCH (m)-[r1]-(direct)
        OPTIONAL MATCH (direct)-[r2]-(indirect)
        WHERE NOT indirect:Parameter
        RETURN m, r1, direct, r2, indirect
        """
        return self._execute_query(query, {"method_name": method_name})

if __name__ == "__main__":
    # 사용 예시
    uri = "neo4j+s://bc50b223.databases.neo4j.io"
    username = "neo4j"             # 기본 사용자 이름
    password = "0mTKomu9ETlWt7JctP2hiPT7FnPfsW7gjV5EFBO6wvI"          # 비밀번호 변경 필요
    
    loader = CodeAnalyzerGraphLoader(uri, username, password)
    
    try:
        json_file_path = "tmp5.json"
        loader.load_project(json_file_path)
        
        # 메서드 질문 예시
        result = loader.find_related_method_nodes("listPods")
        print(f"\n'listPods' 메서드와 연관된 노드: {len(result)}개 찾음")
        
    finally:
        loader.close()