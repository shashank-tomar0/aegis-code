from setuptools import setup, find_packages

setup(
    name="aegiscode",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "google-generativeai",
        "colorama",
        "tabulate",
        "textual>=0.70.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "aegis=aegis.cli:main",
        ],
    },
    author="Antigravity Pair",
    description="AegisCode: An AI-Age Code Integrity & Vetting Agent",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
