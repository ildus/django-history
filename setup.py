from setuptools import setup, find_packages
 
setup(
    name='django-history',
    version='0.1.1',
    description='Django History',
    author='Ildus K.',
    author_email='k-dus@yandex.ru',
    url='https://github.com/django-history',
    packages=find_packages(),
    requires = ['south', 'progressbar'],
    classifiers=[
        'Development Status :: 1 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    include_package_data=True,
    zip_safe=False,
    install_requires=[],
)
