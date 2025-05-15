import os
import json
import javalang  # pip install javalang
from concurrent.futures import ThreadPoolExecutor
from openai_utils import call_openai_api

def find_java_files(project_path):
    """프로젝트 경로에서 모든 Java 파일을 찾습니다."""
    java_files = []
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file.endswith('.java'):
                java_files.append(os.path.join(root, file))
    print(java_files)
    return java_files

def generate_method_description(method_name, method_docs, method_code):
    """OpenAI API를 사용하여 메서드 설명을 생성합니다."""
    prompt = f"""
            다음 Java 메서드에 대한 간결한 설명을 작성해주세요:

            메서드 이름: {method_name}

            문서 주석(Javadoc):
            {method_docs if method_docs else '문서 주석 없음'}

            코드:
            {method_code if method_code else '코드 없음'}

            이 메서드가 무엇을 하는지 한 문장으로 설명해주세요:
            """
    try:
        description = call_openai_api(prompt)
        return description.strip()
    except Exception as e:
        print(f"OpenAI API 호출 오류: {e}")
        return "설명을 생성할 수 없습니다."

def extract_method_body(source_code, method):
    """메서드 본문 코드를 추출합니다."""
    try:
        # 메서드 위치 정보 가져오기
        start_position = method.position
        if not start_position:
            return None
        
        # 메서드 본문 찾기
        start_line = start_position.line - 1  # 0-based indexing
        source_lines = source_code.splitlines()
        
        # 단순화된 방법으로 메서드 본문 추출
        # 중괄호 카운팅으로 메서드 끝 찾기
        body_lines = []
        brace_count = 0
        found_start = False
        
        for line_num, line in enumerate(source_lines[start_line:], start_line):
            if '{' in line and not found_start:
                found_start = True
                brace_count += line.count('{')
                brace_count -= line.count('}')
                if brace_count > 0:
                    body_start_idx = line.find('{') + 1
                    if body_start_idx < len(line):
                        body_lines.append(line[body_start_idx:])
            elif found_start:
                brace_count += line.count('{')
                brace_count -= line.count('}')
                body_lines.append(line)
                
                if brace_count == 0:
                    # 마지막 중괄호 제거
                    if '}' in body_lines[-1]:
                        last_brace_idx = body_lines[-1].rfind('}')
                        body_lines[-1] = body_lines[-1][:last_brace_idx]
                    break
        
        return '\n'.join(body_lines).strip()
    except Exception as e:
        print(f"메서드 본문 추출 에러: {e}")
        return None

def extract_ast_info(tree, source_code=None):
    """AST에서 필요한 정보만 추출합니다."""
    info = {
        'package': None,
        'imports': [],
        'classes': [],
        'interfaces': []
    }
    
    # 패키지 정보
    if tree.package:
        info['package'] = tree.package.name
    
    # 임포트 정보
    for imp in tree.imports:
        info['imports'].append(imp.path)
    
    # 클래스 및 인터페이스 정보
    for path, node in tree.filter(javalang.tree.TypeDeclaration):
        if isinstance(node, javalang.tree.ClassDeclaration):
            class_info = {
                'name': node.name,
                'extends': node.extends.name if node.extends else None,
                'implements': [i.name for i in node.implements] if node.implements else [],
                'methods': [],
                'fields': []  # 클래스 필드 추가
            }
            
            # 필드 추출
            for field in node.fields:
                for declarator in field.declarators:
                    class_info['fields'].append({
                        'name': declarator.name,
                        'type': field.type.name
                    })
            
            # 메서드 추출
            for method in node.methods:
                method_documentation = method.documentation if hasattr(method, 'documentation') else None
                method_code = None
                
                # 메서드 본문 추출
                if source_code:
                    method_code = extract_method_body(source_code, method)
                
                # GPT API로 메서드 설명 생성
                description = generate_method_description(
                    method_name=method.name,
                    method_docs=method_documentation,
                    method_code=method_code
                )
                
                method_info = {
                    'name': method.name,
                    'return_type': method.return_type.name if method.return_type else None,
                    'parameters': [],
                    'documentation': method_documentation,
                    'description': description,
                    'body': method_code
                }
                
                # 파라미터 정보 (타입과 이름)
                if method.parameters:
                    for param in method.parameters:
                        param_info = {
                            'name': param.name,
                            'type': param.type.name if hasattr(param.type, 'name') else str(param.type)
                        }
                        method_info['parameters'].append(param_info)
                
                class_info['methods'].append(method_info)
                
            info['classes'].append(class_info)
            
        elif isinstance(node, javalang.tree.InterfaceDeclaration):
            interface_info = {
                'name': node.name,
                'extends': [e.name for e in node.extends] if node.extends else [],
                'methods': []
            }
            
            # 메서드 추출
            for method in node.methods:
                method_documentation = method.documentation if hasattr(method, 'documentation') else None
                method_code = None
                
                # 메서드 본문 추출
                if source_code:
                    method_code = extract_method_body(source_code, method)
                
                # GPT API로 메서드 설명 생성
                description = generate_method_description(
                    method_name=method.name,
                    method_docs=method_documentation,
                    method_code=method_code
                )
                
                method_info = {
                    'name': method.name,
                    'return_type': method.return_type.name if method.return_type else None,
                    'parameters': [],
                    'documentation': method_documentation,
                    'description': description,
                    'body': method_code
                }
                
                # 파라미터 정보 (타입과 이름)
                if method.parameters:
                    for param in method.parameters:
                        param_info = {
                            'name': param.name,
                            'type': param.type.name if hasattr(param.type, 'name') else str(param.type)
                        }
                        method_info['parameters'].append(param_info)
                
                interface_info['methods'].append(method_info)
                
            info['interfaces'].append(interface_info)
    
    return info

def process_java_file(file_path):
    """Java 파일을 처리하여 AST 정보를 추출합니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            source_code = file.read()
        
        tree = javalang.parse.parse(source_code)
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