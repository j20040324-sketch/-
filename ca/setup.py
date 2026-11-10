from setuptools import find_packages, setup


setup(
    name="prediction-market-lens",
    version="0.1.0",
    description="A small, auditable research pipeline for prediction markets.",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    entry_points={"console_scripts": [
        "market-lens=market_lens.cli:main",
        "market-lens-web=market_lens.web:main",
    ]},
)
