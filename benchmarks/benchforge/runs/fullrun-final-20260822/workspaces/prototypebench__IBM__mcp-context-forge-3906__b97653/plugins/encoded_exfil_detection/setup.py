from setuptools import setup, find_packages

setup(
    name="encoded_exfil_detection",
    version="0.2.0",
    description="Encoded Exfiltration Detection Plugin for MCP",
    author="IBM",
    license="Apache-2.0",
    packages=find_packages(),
    install_requires=[
        "mcp>=0.1.0",
        "pydantic>=2.0.0",
        "typing-extensions>=4.0.0",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
