"""
Configuration loader for FinFlash
Loads and merges configuration from YAML files and environment variables
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and manages application configuration"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize configuration loader
        
        Args:
            config_dir: Path to configuration directory
        """
        self.config_dir = config_dir or Path(__file__).parent
        self.config = {}
        self._loaded = False
        
    def load(self, environment: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration for specified environment
        
        Args:
            environment: Environment name (development, production, testing)
                        If None, will use FLASK_ENV or default to development
                        
        Returns:
            Merged configuration dictionary
        """
        if self._loaded and environment is None:
            return self.config
            
        # Determine environment
        if environment is None:
            environment = os.getenv('FLASK_ENV', 'development')
            
        logger.info(f"Loading configuration for environment: {environment}")
        
        # Load base configuration
        base_config = self._load_yaml_file('config.yaml')
        
        # Load environment-specific configuration
        env_config = {}
        env_file = f"{environment}.yaml"
        if (self.config_dir / env_file).exists():
            env_config = self._load_yaml_file(env_file)
        else:
            logger.warning(f"Environment config file not found: {env_file}")
            
        # Merge configurations (environment overrides base)
        self.config = self._deep_merge(base_config, env_config)
        
        # Override with environment variables
        self._apply_env_overrides()
        
        self._loaded = True
        return self.config
        
    def _load_yaml_file(self, filename: str) -> Dict[str, Any]:
        """Load a YAML configuration file"""
        filepath = self.config_dir / filename
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {filepath}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {filepath}: {e}")
            return {}
            
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries
        
        Args:
            base: Base dictionary
            override: Dictionary with values to override
            
        Returns:
            Merged dictionary
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
                
        return result
        
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration"""
        # Map of environment variables to config paths
        env_mappings = {
            # Database
            'DATABASE_URL': 'database.url',
            'DATABASE_POOL_SIZE': ('database.pool_size', int),
            
            # Redis
            'REDIS_URL': 'redis.url',
            'REDIS_MAX_CONNECTIONS': ('redis.max_connections', int),
            
            # OpenAI
            'OPENAI_API_KEY': 'openai.api_key',
            'OPENAI_MODEL': 'openai.model',
            'OPENAI_TEMPERATURE': ('openai.temperature', float),
            'OPENAI_MAX_TOKENS': ('openai.max_tokens', int),
            
            # Exa
            'EXA_API_KEY': 'exa.api_key',
            'EXA_TIMEOUT': ('exa.timeout', int),
            
            # App settings
            'APP_NAME': 'app.name',
            'APP_VERSION': 'app.version',
            'LOG_LEVEL': 'logging.root.level',
            
            # Server
            'HOST': 'server.host',
            'PORT': ('server.port', int),
            
            # Features
            'ENABLE_WEBSOCKET': ('features.enable_websocket', self._parse_bool),
            'ENABLE_EMAIL_NOTIFICATIONS': ('features.enable_email_notifications', self._parse_bool),
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                if isinstance(config_path, tuple):
                    path, converter = config_path
                    try:
                        value = converter(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid value for {env_var}: {value}")
                        continue
                else:
                    path = config_path
                    
                self._set_nested_value(path, value)
                
    def _set_nested_value(self, path: str, value: Any):
        """Set a nested value in the configuration using dot notation"""
        keys = path.split('.')
        current = self.config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
            
        current[keys[-1]] = value
        
    def _parse_bool(self, value: str) -> bool:
        """Parse boolean from string"""
        return value.lower() in ('true', 'yes', '1', 'on')
        
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            path: Dot-separated path to configuration value
            default: Default value if path not found
            
        Returns:
            Configuration value or default
        """
        if not self._loaded:
            self.load()
            
        keys = path.split('.')
        current = self.config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
                
        return current
        
    def reload(self, environment: Optional[str] = None):
        """Force reload configuration"""
        self._loaded = False
        return self.load(environment)


# Global configuration instance
_config = None


def get_config() -> ConfigLoader:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = ConfigLoader()
    return _config


def load_config(environment: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration for specified environment
    
    Args:
        environment: Environment name
        
    Returns:
        Configuration dictionary
    """
    return get_config().load(environment) 