import setuptools

setuptools.setup(
    name="air_localize_automation",
    version="0.0.1",
    author="Greg M. Fleishman",
    author_email="greg.nli10me@gmail.com",
    description="distributed python wrapper for AirLocalize",
    url="https://github.com/GFleishman/air_localize_automation",
    license="MIT",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=[
        "z5py",
        "numpy",
        "matlab",
    ]
)
