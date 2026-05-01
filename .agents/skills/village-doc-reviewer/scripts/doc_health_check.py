import os
import re
from pathlib import Path

def get_all_resources(project_root):
    resources = set()
    # Directories to ignore
    ignored_dirs = {'.git', '__pycache__', 'node_modules', '.agents', '.gemini', 'docs', 'village-doc-reviewer'}
    
    for root, dirs, files in os.walk(project_root):
        # Filter ignored directories in-place to prevent walking into them
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith('.')]
        
        rel_root = os.path.relpath(root, project_root)
        
        # Add directory as a resource (unless it's the root)
        if rel_root != '.':
            resources.add(rel_root.replace(os.sep, '/'))
        
        for file in files:
            # Ignore Markdown files and hidden files
            if file.endswith('.md') or file.startswith('.'):
                continue
                
            rel_file = os.path.relpath(os.path.join(root, file), project_root)
            resources.add(rel_file.replace(os.sep, '/'))
            
    return resources

def get_referenced_paths(doc_path):
    references = set()
    link_pattern = re.compile(r'\[.*?\]\((.*?)\)')
    
    for root, _, files in os.walk(doc_path):
        for file in files:
            if file.endswith('.md'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    links = link_pattern.findall(content)
                    for link in links:
                        # Clean up fragments and queries
                        link = link.split('#')[0].split('?')[0]
                        if not link.startswith('http'):
                            # Resolve relative path
                            abs_link = os.path.normpath(os.path.join(root, link))
                            rel_to_project = os.path.relpath(abs_link, os.getcwd())
                            references.add(rel_to_project.replace(os.sep, '/'))
    return references

def check_readme_links(readme_path):
    if not os.path.exists(readme_path):
        return set()
    
    link_pattern = re.compile(r'\[.*?\]\((.*?)\)')
    references = set()
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
        links = link_pattern.findall(content)
        for link in links:
            link = link.split('#')[0].split('?')[0]
            if not link.startswith('http'):
                abs_link = os.path.normpath(os.path.join(os.path.dirname(readme_path), link))
                rel_to_project = os.path.relpath(abs_link, os.getcwd())
                references.add(rel_to_project.replace(os.sep, '/'))
    return references

def main():
    project_root = os.getcwd()
    docs_path = os.path.join(project_root, 'docs')
    readme_path = os.path.join(project_root, 'README.md')

    print(f"--- Global Document Health Check ---")
    
    all_resources = get_all_resources(project_root)
    doc_refs = get_referenced_paths(docs_path)
    readme_refs = check_readme_links(readme_path)
    all_refs = doc_refs.union(readme_refs)

    # Check for resources not mentioned in docs
    undocumented = []
    for res in all_resources:
        # A resource is documented if it or one of its parents is referenced
        # or if the reference points directly to it.
        is_documented = False
        for ref in all_refs:
            if res == ref or res.startswith(ref + '/') or ref.startswith(res + '/'):
                is_documented = True
                break
        if not is_documented:
            undocumented.append(res)
    
    if undocumented:
        print(f"\n[!] Undocumented Resources (not found in ./docs or README.md):")
        for res in sorted(undocumented):
            print(f"  - {res}")
    else:
        print(f"\n[v] All project resources are covered by documentation.")

    # Check for broken internal links
    broken_links = []
    for ref in all_refs:
        if ref == '.' or ref == '': continue
        if not os.path.exists(os.path.join(project_root, ref)):
            broken_links.append(ref)
            
    if broken_links:
        print(f"\n[!] Broken Links Found (pointing to non-existent files):")
        for link in sorted(set(broken_links)):
            print(f"  - {link}")
    else:
        print(f"\n[v] No broken internal links found.")

if __name__ == "__main__":
    main()
