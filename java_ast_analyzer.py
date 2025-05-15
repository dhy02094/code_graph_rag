import os
import json
import re
from concurrent.futures import ThreadPoolExecutor

# tree-sitter 라이브러리 임포트
try:
    from tree_sitter import Language, Parser
    import tree_sitter_java as tsjava  # pip install tree-sitter-java
except ImportError:
    print("필요한 라이브러리가 설치되어 있지 않습니다.")
    print("설치하려면:")
    print("pip install tree-sitter")
    print("pip install tree-sitter-java")
    exit(1)

# Java 언어 로드 (aa.py 코드 방식 활용)
try:
    # tree_sitter_java 모듈에서 language 함수 사용
    JAVA_LANGUAGE = Language(tsjava.language())
    parser = Parser()
    parser.set_language(JAVA_LANGUAGE)
except Exception as e:
    print(f"Java 언어 로드 실패: {e}")
    print("tree-sitter-java가 올바르게 설치되어 있는지 확인하세요.")
    print("설치하려면: pip install tree-sitter-java")
    exit(1)

def find_java_files(project_path):
    """프로젝트 경로에서 모든 Java 파일을 찾습니다."""
    java_files = []
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file.endswith('.java'):
                java_files.append(os.path.join(root, file))
    return java_files

def get_node_text(node, source_code):
    """노드의 텍스트를 반환합니다."""
    return source_code[node.start_byte:node.end_byte].decode('utf-8')

def extract_package_name(root_node, source_code):
    """패키지 이름을 추출합니다."""
    package_declaration = next((node for node in root_node.children 
                                if node.type == 'package_declaration'), None)
    if package_declaration:
        # 'package' 키워드 다음의 이름 부분 찾기
        for child in package_declaration.children:
            if child.type == 'scoped_identifier':
                return get_node_text(child, source_code)
    return None

def extract_imports(root_node, source_code):
    """임포트 정보를 추출합니다."""
    imports = []
    for node in root_node.children:
        if node.type == 'import_declaration':
            # 'import' 키워드 다음의 이름 부분 찾기
            for child in node.children:
                if child.type == 'scoped_identifier':
                    imports.append(get_node_text(child, source_code))
                    break
    return imports

def extract_method_parameters(method_node, source_code):
    """메서드 파라미터 정보를 추출합니다."""
    parameters = []
    formal_parameters = next((child for child in method_node.children 
                             if child.type == 'formal_parameters'), None)
    if formal_parameters:
        for child in formal_parameters.children:
            if child.type == 'formal_parameter':
                param_name = None
                param_type = None
                
                # 타입 찾기
                type_node = next((n for n in child.children if n.type in 
                               ['type_identifier', 'array_type', 'primitive_type']), None)
                if type_node:
                    param_type = get_node_text(type_node, source_code)
                
                # 이름 찾기
                name_node = next((n for n in child.children if n.type == 'identifier'), None)
                if name_node:
                    param_name = get_node_text(name_node, source_code)
                
                if param_name and param_type:
                    parameters.append({
                        'name': param_name,
                        'type': param_type
                    })
    
    return parameters

def extract_method_body(method_node, source_code):
    """메서드 본문을 추출합니다."""
    body_node = next((child for child in method_node.children 
                     if child.type == 'block'), None)
    if body_node:
        return get_node_text(body_node, source_code)
    return None

def find_object_references(method_body):
    """메서드 본문에서 객체 참조를 추출합니다."""
    if not method_body:
        return []
    
    # 'new ClassName(' 패턴 찾기
    new_objects = re.findall(r'new\s+([A-Za-z][A-Za-z0-9_]*)\s*\(', method_body)
    
    # 'ClassName.method' 패턴 찾기
    static_calls = re.findall(r'([A-Za-z][A-Za-z0-9_]*)\s*\.\s*[A-Za-z][A-Za-z0-9_]*\s*\(', method_body)
    
    # 변수 선언 'ClassName variable' 패턴 찾기
    var_declarations = re.findall(r'([A-Za-z][A-Za-z0-9_]*)\s+[a-z][A-Za-z0-9_]*\s*[=;]', method_body)
    
    # 중복 제거 및 통합
    ref_objects = set(new_objects + static_calls + var_declarations)
    
    # primitive 타입 제외
    primitives = {'int', 'long', 'double', 'float', 'boolean', 'char', 'byte', 'short', 'void', 'String'}
    ref_objects = [obj for obj in ref_objects if obj not in primitives]
    
    return list(ref_objects)

def extract_class_methods(class_node, source_code):
    """클래스의 메서드 정보를 추출합니다."""
    methods = []
    
    for child in class_node.children:
        if child.type == 'class_body':
            for body_child in child.children:
                if body_child.type == 'method_declaration':
                    # 반환 타입 찾기
                    return_type_node = next((n for n in body_child.children 
                                           if n.type in ['type_identifier', 'void_type', 'primitive_type']), None)
                    return_type = get_node_text(return_type_node, source_code) if return_type_node else None
                    
                    # 메서드 이름 찾기
                    name_node = next((n for n in body_child.children if n.type == 'identifier'), None)
                    if name_node:
                        method_name = get_node_text(name_node, source_code)
                        
                        # 파라미터 추출
                        parameters = extract_method_parameters(body_child, source_code)
                        
                        # 메서드 본문 추출
                        method_body = extract_method_body(body_child, source_code)
                        
                        # 객체 참조 찾기
                        referenced_objects = find_object_references(method_body)
                        
                        methods.append({
                            'name': method_name,
                            'return_type': return_type,
                            'parameters': parameters,
                            'body': method_body,
                            'referenced_objects': referenced_objects
                        })
    
    return methods

def extract_interface_methods(interface_node, source_code):
    """인터페이스의 메서드 정보를 추출합니다."""
    methods = []
    
    for child in interface_node.children:
        if child.type == 'interface_body':
            for body_child in child.children:
                if body_child.type == 'method_declaration':
                    # 반환 타입 찾기
                    return_type_node = next((n for n in body_child.children 
                                           if n.type in ['type_identifier', 'void_type', 'primitive_type']), None)
                    return_type = get_node_text(return_type_node, source_code) if return_type_node else None
                    
                    # 메서드 이름 찾기
                    name_node = next((n for n in body_child.children if n.type == 'identifier'), None)
                    if name_node:
                        method_name = get_node_text(name_node, source_code)
                        
                        # 파라미터 추출
                        parameters = extract_method_parameters(body_child, source_code)
                        
                        methods.append({
                            'name': method_name,
                            'return_type': return_type,
                            'parameters': parameters
                        })
    
    return methods

def extract_class_fields(class_node, source_code):
    """클래스의 필드 정보를 추출합니다."""
    fields = []
    
    for child in class_node.children:
        if child.type == 'class_body':
            for body_child in child.children:
                if body_child.type == 'field_declaration':
                    # 필드 타입 찾기
                    type_node = next((n for n in body_child.children 
                                    if n.type in ['type_identifier', 'primitive_type']), None)
                    field_type = get_node_text(type_node, source_code) if type_node else None
                    
                    # 필드 이름 찾기
                    for n in body_child.children:
                        if n.type == 'variable_declarator':
                            name_node = next((c for c in n.children if c.type == 'identifier'), None)
                            if name_node:
                                field_name = get_node_text(name_node, source_code)
                                fields.append({
                                    'name': field_name,
                                    'type': field_type
                                })
    
    return fields

def extract_class_extends(class_node, source_code):
    """클래스의 확장(extends) 정보를 추출합니다."""
    extends_clause = next((child for child in class_node.children 
                          if child.type == 'superclass'), None)
    if extends_clause:
        type_node = next((n for n in extends_clause.children 
                         if n.type == 'type_identifier'), None)
        if type_node:
            return get_node_text(type_node, source_code)
    return None

def extract_class_implements(class_node, source_code):
    """클래스의 구현(implements) 정보를 추출합니다."""
    implements = []
    implements_clause = next((child for child in class_node.children 
                             if child.type == 'interfaces'), None)
    if implements_clause:
        for child in implements_clause.children:
            if child.type == 'type_identifier':
                implements.append(get_node_text(child, source_code))
    return implements

def extract_interface_extends(interface_node, source_code):
    """인터페이스의 확장(extends) 정보를 추출합니다."""
    extends = []
    extends_clause = next((child for child in interface_node.children 
                          if child.type == 'extends_interfaces'), None)
    if extends_clause:
        for child in extends_clause.children:
            if child.type == 'type_identifier':
                extends.append(get_node_text(child, source_code))
    return extends

def extract_ast_info(tree, source_code):
    """AST에서 필요한 정보만 추출합니다."""
    root_node = tree.root_node
    
    info = {
        'package': extract_package_name(root_node, source_code),
        'imports': extract_imports(root_node, source_code),
        'classes': [],
        'interfaces': [],
        'object_references': []
    }
    
    # 클래스 및 인터페이스 정보
    for node in root_node.children:
        if node.type == 'class_declaration':
            # 클래스 이름 추출
            name_node = next((child for child in node.children if child.type == 'identifier'), None)
            if name_node:
                class_name = get_node_text(name_node, source_code)
                
                # 클래스 정보 구성
                class_info = {
                    'name': class_name,
                    'extends': extract_class_extends(node, source_code),
                    'implements': extract_class_implements(node, source_code),
                    'fields': extract_class_fields(node, source_code),
                    'methods': extract_class_methods(node, source_code)
                }
                
                # 객체 참조 정보 추가
                for method_info in class_info['methods']:
                    for ref_obj in method_info.get('referenced_objects', []):
                        if ref_obj != class_name:  # 자기 자신 참조 제외
                            info['object_references'].append({
                                'class': class_name,
                                'method': method_info['name'],
                                'referenced_object': ref_obj
                            })
                
                info['classes'].append(class_info)
                
        elif node.type == 'interface_declaration':
            # 인터페이스 이름 추출
            name_node = next((child for child in node.children if child.type == 'identifier'), None)
            if name_node:
                interface_name = get_node_text(name_node, source_code)
                
                # 인터페이스 정보 구성
                interface_info = {
                    'name': interface_name,
                    'extends': extract_interface_extends(node, source_code),
                    'methods': extract_interface_methods(node, source_code)
                }
                
                info['interfaces'].append(interface_info)
    
    return info

def process_java_file(file_path):
    """Java 파일을 처리하여 AST 정보를 추출합니다."""
    try:
        # 파일 읽기
        with open(file_path, 'rb') as file:
            source_code = file.read()
        
        # aa.py 스타일의 파싱 방식 적용
        def read_callable_byte_offset(byte_offset, point):
            return source_code[byte_offset : byte_offset + 1]
            
        # 새로운 방식으로 파싱
        tree = parser.parse(read_callable_byte_offset, encoding="utf8")
        
        # AST 정보 추출
        ast_info = extract_ast_info(tree, source_code)
        ast_info['path'] = file_path
        return ast_info
    except Exception as e:
        print(f"파싱 에러 ({file_path}): {e}")
        return {'path': file_path, 'error': str(e)}

def analyze_java_project(project_path, output_json=None, max_workers=4):
    """Java 프로젝트를 분석합니다."""
    java_files = find_java_files(project_path)
    print(f"총 {len(java_files)}개의 Java 파일을 찾았습니다.")
    
    project_structure = {
        'project_path': project_path,
        'files': {}
    }
    
    # 병렬 처리를 통한 성능 개선
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, file_path in enumerate(java_files):
            relative_path = os.path.relpath(file_path, project_path)
            print(f"파싱 중: {relative_path} ({i+1}/{len(java_files)})")
            
            project_structure['files'][relative_path] = executor.submit(process_java_file, file_path).result()
    
    # 관계 분석
    analyze_relationships(project_structure)
    
    # 객체 참조 관계 추가 분석
    analyze_object_references(project_structure)
    
    # JSON으로 저장
    if output_json:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(project_structure, f, indent=2, ensure_ascii=False)
        print(f"프로젝트 구조가 {output_json}에 저장되었습니다.")
    
    return project_structure

def analyze_relationships(project_structure):
    """파일 간의 관계를 분석합니다."""
    # 클래스 맵 구성 (클래스 이름 -> 파일 경로)
    class_map = {}
    
    for file_path, file_info in project_structure['files'].items():
        if 'error' in file_info:
            continue
            
        package = file_info.get('package', '')
        
        for class_info in file_info.get('classes', []):
            full_class_name = f"{package}.{class_info['name']}" if package else class_info['name']
            class_map[full_class_name] = file_path
            # 짧은 클래스 이름도 맵에 추가 (패키지 없이)
            class_map[class_info['name']] = file_path
            
        for interface_info in file_info.get('interfaces', []):
            full_interface_name = f"{package}.{interface_info['name']}" if package else interface_info['name']
            class_map[full_interface_name] = file_path
            class_map[interface_info['name']] = file_path
    
    # 의존성 분석
    for file_path, file_info in project_structure['files'].items():
        if 'error' in file_info:
            continue
            
        dependencies = []
        
        # 임포트 의존성 (내부 프로젝트 내 임포트만 포함)
        for import_path in file_info.get('imports', []):
            # 프로젝트 내부 임포트인지 확인
            is_internal = False
            
            # 패키지의 일부만 있는 경우 체크
            for class_name in class_map.keys():
                if import_path.endswith(class_name) or class_name in import_path.split('.'):
                    is_internal = True
                    break
            
            if is_internal or import_path in class_map:
                dependency = {'type': 'import', 'target': import_path}
                
                # 임포트된 클래스가 프로젝트 내에 있는지 확인
                if import_path in class_map:
                    dependency['file'] = class_map[import_path]
                    
                dependencies.append(dependency)
        
        # 상속 의존성
        for class_info in file_info.get('classes', []):
            if class_info.get('extends'):
                dependency = {'type': 'extends', 'target': class_info['extends']}
                
                if class_info['extends'] in class_map:
                    dependency['file'] = class_map[class_info['extends']]
                    
                dependencies.append(dependency)
            
            # 구현 의존성
            for interface in class_info.get('implements', []):
                dependency = {'type': 'implements', 'target': interface}
                
                if interface in class_map:
                    dependency['file'] = class_map[interface]
                    
                dependencies.append(dependency)
        
        file_info['dependencies'] = dependencies

def analyze_object_references(project_structure):
    """객체 참조 관계를 분석합니다."""
    # 클래스 맵 구성 (클래스 이름 -> 파일 경로)
    class_map = {}
    
    for file_path, file_info in project_structure['files'].items():
        if 'error' in file_info:
            continue
            
        package = file_info.get('package', '')
        
        for class_info in file_info.get('classes', []):
            full_class_name = f"{package}.{class_info['name']}" if package else class_info['name']
            class_map[full_class_name] = file_path
            class_map[class_info['name']] = file_path
            
        for interface_info in file_info.get('interfaces', []):
            full_interface_name = f"{package}.{interface_info['name']}" if package else interface_info['name']
            class_map[full_interface_name] = file_path
            class_map[interface_info['name']] = file_path
    
    # 객체 참조 관계 분석
    for file_path, file_info in project_structure['files'].items():
        if 'error' in file_info or 'object_references' not in file_info:
            continue
            
        object_references = []
        
        for ref in file_info.get('object_references', []):
            ref_obj = ref['referenced_object']
            
            # 내부 프로젝트 객체인지 확인
            if ref_obj in class_map:
                object_references.append({
                    'from_class': ref['class'],
                    'from_method': ref['method'],
                    'to_class': ref_obj,
                    'to_file': class_map[ref_obj]
                })
        
        file_info['object_references'] = object_references

if __name__ == "__main__":
    import sys
    import time
    
    if len(sys.argv) < 2:
        print("사용법: python java_ast_analyzer.py <분석할_프로젝트_경로> [결과_저장_JSON_파일]")
        sys.exit(1)
    
    project_path = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else None
    
    start_time = time.time()
    analyze_java_project(project_path, output_json)
    end_time = time.time()
    
    print(f"분석 완료! 실행 시간: {end_time - start_time:.2f}초") 