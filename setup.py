from setuptools import setup

setup(
    name='starnearyou',
    version='0.1.dev',
    py_modules=['starnearyou'],
    install_requires=[
        'Click',
        'lxml',
        'Pillow',
        'requests',
        'twython',
    ],
    entry_points="""
        [console_scripts]
        starnearyou=starnearyou:cli
    """,
)
