"""
Repository intelligence analyzer for detecting project type, framework, and structure.
"""
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import json
import re
from collections import defaultdict

from ..core.logging import get_logger

logger = get_logger(__name__)


# Framework detection patterns
FRAMEWORK_PATTERNS = {
    'fastapi': {
        'files': ['main.py', 'app.py'],
        'imports': ['from fastapi import', 'import fastapi'],
        'indicators': ['FastAPI(', '@app.get', '@app.post']
    },
    'flask': {
        'files': ['app.py', 'wsgi.py'],
        'imports': ['from flask import', 'import flask'],
        'indicators': ['Flask(', '@app.route']
    },
    'django': {
        'files': ['manage.py', 'settings.py', 'wsgi.py'],
        'imports': ['from django', 'import django'],
        'indicators': ['INSTALLED_APPS', 'MIDDLEWARE']
    },
    'react': {
        'files': ['package.json'],
        'imports': ['from react', "from 'react'", 'import react', "import 'react'"],
        'indicators': ['React.Component', 'useState', 'useEffect'],
        'package_deps': ['react', 'react-dom']
    },
    'nextjs': {
        'files': ['next.config.js', 'next.config.ts'],
        'imports': ['from next', "from 'next'"],
        'indicators': ['export default function', 'getServerSideProps', 'getStaticProps'],
        'package_deps': ['next']
    },
    'vue': {
        'files': ['vue.config.js'],
        'imports': ['from vue', "from 'vue'"],
        'indicators': ['createApp', 'Vue.component'],
        'package_deps': ['vue']
    },
    'angular': {
        'files': ['angular.json'],
        'imports': ['from @angular'],
        'indicators': ['@Component', '@NgModule'],
        'package_deps': ['@angular/core']
    },
    'express': {
        'files': ['server.js', 'app.js'],
        'imports': ['from express', "from 'express'", 'require("express")', "require('express')"],
        'indicators': ['express()', 'app.listen'],
        'package_deps': ['express']
    },
    'spring-boot': {
        'files': ['pom.xml', 'build.gradle'],
        'imports': ['import org.springframework'],
        'indicators': ['@SpringBootApplication', '@RestController', '@Service']
    },
    'laravel': {
        'files': ['artisan', 'composer.json'],
        'imports': ['use Illuminate'],
        'indicators': ['namespace App\\', 'Route::']
    }
}

# Entry point patterns by language
ENTRY_POINT_PATTERNS = {
    'python': ['main.py', 'app.py', '__main__.py', 'wsgi.py', 'asgi.py', 'manage.py'],
    'javascript': ['index.js', 'main.js', 'app.js', 'server.js'],
    'typescript': ['index.ts', 'main.ts', 'app.ts', 'server.ts'],
    'java': ['Main.java', 'Application.java', 'App.java'],
    'go': ['main.go'],
    'rust': ['main.rs'],
    'php': ['index.php', 'artisan']
}

# Dependency file patterns
DEPENDENCY_FILES = {
    'python': ['requirements.txt', 'Pipfile', 'pyproject.toml', 'setup.py', 'poetry.lock'],
    'javascript': ['package.json', 'package-lock.json', 'yarn.lock'],
    'java': ['pom.xml', 'build.gradle', 'build.gradle.kts'],
    'ruby': ['Gemfile', 'Gemfile.lock'],
    'php': ['composer.json', 'composer.lock'],
    'go': ['go.mod', 'go.sum'],
    'rust': ['Cargo.toml', 'Cargo.lock'],
    'csharp': ['*.csproj', 'packages.config']
}


class RepositoryAnalyzer:
    """Analyzes repository structure and detects project characteristics."""
    
    def __init__(self, project_path: Path, progress_tracker=None):
        self.project_path = project_path
        self.files_map: Dict[str, List[Path]] = defaultdict(list)
        self.language_stats: Dict[str, int] = defaultdict(int)
        self.total_lines = 0
        self.total_files = 0
        self.progress_tracker = progress_tracker
        
    def analyze(self) -> Dict:
        """
        Perform comprehensive repository analysis.
        
        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Starting repository analysis for: {self.project_path}")
        
        if self.progress_tracker:
            self.progress_tracker.start_stage('scanning', 'Scanning repository files...')
        
        # Scan all files
        self._scan_files()
        
        if self.progress_tracker:
            self.progress_tracker.milestone_complete('Scanning', f'Found {self.total_files} code files')
            self.progress_tracker.start_stage('analyzing', 'Analyzing repository structure...')
        
        # Detect primary language
        primary_language = self._detect_primary_language()
        
        if self.progress_tracker:
            self.progress_tracker.emit_info(f'Primary language detected: {primary_language}')
        
        # Detect framework
        framework = self._detect_framework()
        
        if self.progress_tracker and framework:
            self.progress_tracker.emit_info(f'Framework detected: {framework}')
        
        # Find entry points
        entry_points = self._find_entry_points()
        
        # Parse dependencies
        dependencies = self._parse_dependencies()
        
        # Detect API endpoints
        api_endpoints = self._detect_api_endpoints()
        
        # Detect models/entities
        models = self._detect_models()
        
        # Determine repository type
        repo_type = self._determine_repository_type(primary_language, framework)
        
        # Calculate language breakdown
        language_breakdown = self._calculate_language_breakdown()
        
        # Detect architecture patterns
        architecture = self._detect_architecture()
        
        if self.progress_tracker:
            self.progress_tracker.milestone_complete('Analysis', 'Repository intelligence complete')
        
        analysis_result = {
            'repository_type': repo_type,
            'framework': framework,
            'entry_points': entry_points,
            'total_files': self.total_files,
            'total_lines_of_code': self.total_lines,
            'languages_breakdown': language_breakdown,
            'dependencies': dependencies,
            'api_endpoints_count': api_endpoints['count'],
            'models_count': len(models),
            'architecture': architecture,
            'primary_language': primary_language,
            'api_endpoints_details': api_endpoints['endpoints'][:10],  # First 10 for display
            'models_list': models[:10],  # First 10 for display
            'important_files': self._identify_important_files()
        }
        
        logger.info(f"Analysis complete: {repo_type} with {framework or 'no framework detected'}")
        return analysis_result
    
    def _scan_files(self):
        """Scan all files and categorize by extension."""
        code_extensions = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.c': 'c',
            '.cpp': 'cpp',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php'
        }
        
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build'}
        
        # First pass: count total code files for progress tracking
        all_files_list = list(self.project_path.rglob('*'))
        code_file_count = 0
        for fp in all_files_list:
            if fp.is_file():
                if any(skip_dir in fp.parts for skip_dir in skip_dirs):
                    continue
                if fp.suffix.lower() in code_extensions:
                    code_file_count += 1
        
        if self.progress_tracker:
            self.progress_tracker.set_total_files(code_file_count)
        
        file_index = 0
        for file_path in all_files_list:
            if file_path.is_file():
                # Skip if in skip directory
                if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                    continue
                
                ext = file_path.suffix.lower()
                if ext in code_extensions:
                    language = code_extensions[ext]
                    self.files_map[language].append(file_path)
                    self.total_files += 1
                    file_index += 1
                    
                    # Update progress every file
                    if self.progress_tracker:
                        self.progress_tracker.update_file_progress(file_path.name, file_index)
                    
                    # Count lines
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = len(f.readlines())
                            self.language_stats[language] += lines
                            self.total_lines += lines
                    except Exception as e:
                        if self.progress_tracker:
                            self.progress_tracker.emit_warning(f'Could not read file', file_path.name)
                        pass
    
    def _detect_primary_language(self) -> str:
        """Determine the primary programming language."""
        if not self.language_stats:
            return 'unknown'
        
        return max(self.language_stats, key=self.language_stats.get)
    
    def _detect_framework(self) -> Optional[str]:
        """Detect the framework used in the project."""
        detected_frameworks = []
        
        for framework, patterns in FRAMEWORK_PATTERNS.items():
            score = 0
            
            # Check for specific files
            for file_pattern in patterns.get('files', []):
                if list(self.project_path.rglob(file_pattern)):
                    score += 2
            
            # Check for imports and indicators in code files
            for language, files in self.files_map.items():
                for file_path in files[:20]:  # Check first 20 files of each language
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            
                            # Check imports
                            for import_pattern in patterns.get('imports', []):
                                if import_pattern in content:
                                    score += 3
                                    break
                            
                            # Check indicators
                            for indicator in patterns.get('indicators', []):
                                if indicator in content:
                                    score += 1
                    except:
                        pass
            
            # Check package.json for JS frameworks
            if 'package_deps' in patterns:
                package_json = self.project_path / 'package.json'
                if package_json.exists():
                    try:
                        with open(package_json, 'r', encoding='utf-8') as f:
                            package_data = json.load(f)
                            deps = {**package_data.get('dependencies', {}), 
                                   **package_data.get('devDependencies', {})}
                            
                            for dep in patterns['package_deps']:
                                if dep in deps:
                                    score += 5
                    except:
                        pass
            
            if score > 0:
                detected_frameworks.append((framework, score))
        
        if detected_frameworks:
            # Return framework with highest score
            detected_frameworks.sort(key=lambda x: x[1], reverse=True)
            return detected_frameworks[0][0]
        
        return None
    
    def _find_entry_points(self) -> List[str]:
        """Find entry point files."""
        entry_points = []
        
        for language, patterns in ENTRY_POINT_PATTERNS.items():
            for pattern in patterns:
                matches = list(self.project_path.rglob(pattern))
                for match in matches:
                    relative_path = str(match.relative_to(self.project_path))
                    if relative_path not in entry_points:
                        entry_points.append(relative_path)
        
        return entry_points[:5]  # Return top 5
    
    def _parse_dependencies(self) -> List[str]:
        """Parse and extract dependencies from dependency files."""
        dependencies = []
        
        # Python requirements.txt
        req_file = self.project_path / 'requirements.txt'
        if req_file.exists():
            try:
                with open(req_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Extract package name (before ==, >=, etc.)
                            dep = re.split(r'[=<>!]', line)[0].strip()
                            if dep:
                                dependencies.append(dep)
            except:
                pass
        
        # Python pyproject.toml
        pyproject = self.project_path / 'pyproject.toml'
        if pyproject.exists():
            try:
                with open(pyproject, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Simple regex to find dependencies
                    deps = re.findall(r'"([a-zA-Z0-9\-_]+)[>=<]', content)
                    dependencies.extend(deps)
            except:
                pass
        
        # JavaScript package.json
        package_json = self.project_path / 'package.json'
        if package_json.exists():
            try:
                with open(package_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    deps = list(data.get('dependencies', {}).keys())
                    dev_deps = list(data.get('devDependencies', {}).keys())
                    dependencies.extend(deps + dev_deps)
            except:
                pass
        
        return list(set(dependencies))[:20]  # Return unique, max 20
    
    def _detect_api_endpoints(self) -> Dict:
        """Detect API endpoints in the codebase."""
        endpoints = []
        patterns = [
            r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',  # FastAPI/Flask
            r'@(Get|Post|Put|Delete|Patch)Mapping\(["\']([^"\']+)["\']',  # Spring Boot
            r'Route::(get|post|put|delete|patch)\(["\']([^"\']+)["\']',  # Laravel
            r'app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',  # Express
        ]
        
        for language, files in self.files_map.items():
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, content)
                            for match in matches:
                                if isinstance(match, tuple):
                                    method = match[0].upper()
                                    path = match[1] if len(match) > 1 else ''
                                    endpoints.append({
                                        'method': method,
                                        'path': path,
                                        'file': str(file_path.relative_to(self.project_path))
                                    })
                except:
                    pass
        
        return {
            'count': len(endpoints),
            'endpoints': endpoints
        }
    
    def _detect_models(self) -> List[str]:
        """Detect data models/entities in the codebase."""
        models = []
        
        # Python models (SQLAlchemy, Django, etc.)
        python_patterns = [
            r'class\s+(\w+)\([^)]*(?:Base|Model|models\.Model)[^)]*\):',
            r'class\s+(\w+)\([^)]*BaseModel[^)]*\):',
        ]
        
        # Java entities
        java_patterns = [
            r'@Entity\s+public\s+class\s+(\w+)',
            r'class\s+(\w+)\s+implements\s+Serializable'
        ]
        
        for language, files in self.files_map.items():
            patterns = python_patterns if language == 'python' else java_patterns if language == 'java' else []
            
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, content)
                            models.extend(matches)
                except:
                    pass
        
        return list(set(models))
    
    def _determine_repository_type(self, primary_language: str, framework: Optional[str]) -> str:
        """Determine the repository type based on language and framework."""
        
        # Check if it's a backend project
        backend_indicators = ['fastapi', 'flask', 'django', 'express', 'spring-boot', 'laravel']
        frontend_indicators = ['react', 'vue', 'angular', 'nextjs']
        
        if framework in backend_indicators:
            return f"{primary_language.capitalize()} Backend"
        elif framework in frontend_indicators:
            return f"{framework.capitalize()} Frontend"
        elif primary_language == 'python':
            return "Python Application"
        elif primary_language in ['javascript', 'typescript']:
            return "JavaScript Application"
        elif primary_language == 'java':
            return "Java Application"
        else:
            return f"{primary_language.capitalize()} Project"
    
    def _calculate_language_breakdown(self) -> Dict[str, float]:
        """Calculate percentage breakdown of languages."""
        if self.total_lines == 0:
            return {}
        
        breakdown = {}
        for language, lines in self.language_stats.items():
            percentage = round((lines / self.total_lines) * 100, 1)
            breakdown[language] = percentage
        
        return breakdown
    
    def _detect_architecture(self) -> str:
        """Detect architecture pattern."""
        has_models = bool(self._detect_models())
        has_api = bool(self._detect_api_endpoints()['count'] > 0)
        
        # Check for common directory structures
        has_mvc_structure = all([
            (self.project_path / d).exists() 
            for d in ['models', 'views', 'controllers']
        ]) or all([
            (self.project_path / 'app' / d).exists() 
            for d in ['models', 'views', 'controllers']
        ])
        
        has_modular_structure = len(list(self.project_path.glob('*/models.py'))) > 1
        
        if has_mvc_structure:
            return "MVC"
        elif has_modular_structure:
            return "Modular Architecture"
        elif has_api and has_models:
            return "API-Driven Architecture"
        else:
            return "Monolithic"
    
    def _identify_important_files(self) -> List[str]:
        """Identify important files in the repository."""
        important = []
        
        important_patterns = [
            'README.md', 'README.rst', 'README.txt',
            'requirements.txt', 'package.json', 'pom.xml',
            'Dockerfile', 'docker-compose.yml',
            '.env.example', 'config.py', 'settings.py',
            'main.py', 'app.py', 'index.js', 'index.ts'
        ]
        
        for pattern in important_patterns:
            matches = list(self.project_path.rglob(pattern))
            for match in matches[:1]:  # Only first occurrence
                important.append(str(match.relative_to(self.project_path)))
        
        return important[:10]


def analyze_repository(project_path: Path, progress_tracker=None) -> Dict:
    """
    Convenience function to analyze a repository.
    
    Args:
        project_path: Path to the project directory
        progress_tracker: Optional ProgressTracker instance
    
    Returns:
        Dictionary with analysis results
    """
    analyzer = RepositoryAnalyzer(project_path, progress_tracker)
    return analyzer.analyze()
