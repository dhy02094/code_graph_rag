import os
import json
import javalang  # pip install javalang
from concurrent.futures import ThreadPoolExecutor

def find_java_files(project_path):
    """프로젝트 경로에서 모든 Java 파일을 찾습니다."""
    java_files = []
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file.endswith('.java'):
                java_files.append(os.path.join(root, file))
    return java_files

def extract_ast_info(tree):
    """AST에서 필요한 정보만 추출합니다."""
    info = {
        'package': None,
        'imports': [],
        'classes': [],
        'interfaces': [],
        'methods': []
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
                'methods': []
            }
            
            # 메서드 추출
            for method in node.methods:
                class_info['methods'].append({
                    'name': method.name,
                    'return_type': method.return_type.name if method.return_type else None,
                    'parameters': [p.name for p in method.parameters] if method.parameters else []
                })
                
            info['classes'].append(class_info)
            
        elif isinstance(node, javalang.tree.InterfaceDeclaration):
            interface_info = {
                'name': node.name,
                'extends': [e.name for e in node.extends] if node.extends else [],
                'methods': []
            }
            
            # 메서드 추출
            for method in node.methods:
                interface_info['methods'].append({
                    'name': method.name,
                    'return_type': method.return_type.name if method.return_type else None,
                    'parameters': [p.name for p in method.parameters] if method.parameters else []
                })
                
            info['interfaces'].append(interface_info)
    
    return info

def process_java_file(file_path):
    """Java 파일을 처리하여 AST 정보를 추출합니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            source_code = file.read()
        
        tree = javalang.parse.parse(source_code)
        ast_info = extract_ast_info(tree)
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
    
    # 의존성 분석
    for file_path, file_info in project_structure['files'].items():
        if 'error' in file_info:
            continue
            
        dependencies = []
        
        # 임포트 의존성
        for import_path in file_info.get('imports', []):
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