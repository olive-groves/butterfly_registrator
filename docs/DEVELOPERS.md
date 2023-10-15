# Developers

## Contributing to `butterfly_registrator`

You can contribute to `butterfly_registrator` with a pull request by following these steps:

1. Fork the [repo<sup>↗</sup>](https://github.com/olive-groves/butterfly_registrator).
2. Create a branch: `git checkout -b <branch_name>`.
3. Make your changes and commit them: `git commit -m '<commit_message>'`
4. Push to the original branch: `git push origin <project_name>/<location>`
5. Create the pull request.

Or see the GitHub documentation on [creating a pull request<sup>↗</sup>](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request).

## Creating the executable and setup installer

The installer executable for Butterfly Registrator is created by first bundling the app with PyInstaller and then creating a setup installer with Inno Setup.

### Install PyInstaller

PyInstaller must be installed with the same packages as the environment of the Butterfly Registrator to bundle a functioning dist and executable.

With ```conda``` you can do this by cloning the environment you use for Registrator, activating that clone, and then installing PyInstaller. 

#### Cloning from `env` subfolder

If you use an `env` subfolder in the root of `butterfly_registrator` for your Registrator environment, first open Anaconda Prompt and change the directory to the root directory.

```
cd C:\path\to\the\butterfly_registrator\
```

Clone the environment into a new subfolder named `env_installer`, using the full directory of `env` in the command.

```
conda create --prefix ./env_installer --clone C:\path\to\the\butterfly_registrator\env
```

Activate the environment.

```
conda activate ./env_installer
```

#### Cloning from `environment.yml`

You can also create and activate a clone of the environment directly from the ```environment.yml``` in the root directory of ```butterfly_registrator```:

into a subfolder;
```
conda env create --file environment.yml --prefix ./env_installer
conda activate ./env_installer
```

or in a new named environment.
```
conda env create --file environment.yml --name registrator_installer
conda activate registrator_installer
```

#### Install

With the installer environment activated, install PyInstaller:
```
conda install pyinstaller
```

### Run PyInstaller to bundle Butterfly Registrator

Run PyInstaller with the following command while in the **source code** directory ```\butterfly_registrator\butterfly_registrator```.

```
cd butterfly_registrator
pyinstaller --onedir --windowed --icon=icons\icon.ico butterfly_registrator.py
```

> PyInstaller not working? Make sure you've changed directory to the source code directory (the subfolder `butterfly_registrator` within the repo itself).

The executable runs fastest when not bundled into one file (otherwise it needs to unpack all packages on each startup), so we enforce the default ```--onedir```. We also enforce ```--windowed``` to prevent the console window from opening when the executable runs. We add the app icon with the ```--icon``` argument.

### Use Inno Setup to create a setup installer

Steps to use Inno Setup are not yet documented.

## Generating documentation with pdoc

The docs branch is exclusively for generating documentation with pdoc.

In other words, it is a one-way street to docs: only pull main into docs; never pull docs into main.

> Note: We use [pdoc](https://pdoc.dev/), *not* pdoc3.

### 0. Pull main into docs

Bring the latest code into the docs branch with a pull request main>docs.

### 1. Checkout docs branch

Checkout the docs branch.

### 2. Open conda and change directory to the root folder of butterfly_registrator

```
cd C:\butterfly_registrator
```

### 3. (If not yet done) Install docs environment

Install the docs environment with conda using environment_docs.yml, which is a modified version of the Butterfly Registrator's base environment with pdoc and Python 3.7 (which is required for pdoc). This .yml is available in the docs branch. :

```
conda env create -f environment_docs.yml --prefix ./env_docs
```

### 4. Add `"Returns"` to pdoc Google docstring sections

pdoc does not include **Returns** in its list of section headers for Google's docstring style guide. This means the returns are not styled like those under **Arguments**. 

To give that styling to returns, do this:
1. Locate `docstrings.py` in the pdoc site package which installed with the docs environment, likely here:

```
...\env_docs\Lib\site-packages\pdoc\docstrings.py
```

2. Add `"Returns"` to the list variable `GOOGLE_LIST_SECTIONS`, which is around line 80 or so.

```
GOOGLE_LIST_SECTIONS = ["Args", "Raises", "Attributes", "Returns"]
```

3. Save `docstrings.py`

### 5. Activate docs environment 

```
conda activate ./env_docs
```

### 6. Add to path the butterfly_registrator source folder

```
set PYTHONPATH=C:\butterfly_registrator\butterfly_registrator
```

### 7. Change directory to source folder

```
cd butterfly_registrator
```

### 8. Run pdoc

Run pdoc with the following command while in the source code directory ```\butterfly_registrator\butterfly_registrator```:

```
pdoc C:\butterfly_registrator\butterfly_registrator -t C:\butterfly_registrator\docs\_templates --docformat google --logo https://olive-groves.github.io/butterfly_registrator/images/registrator_logo.png --logo-link https://olive-groves.github.io/butterfly_registrator/ --favicon https://olive-groves.github.io/butterfly_registrator/images/registrator_logo.png -o C:\butterfly_registrator\docs\
```

> You will need to edit the full directory of the repo in the above pdoc command (`C:\butterfly_registrator\...`) to match that on your machine.

We call the custom templates folder with ```-t```. We enforce the google docstring format with ```--docformat```. We add the webpage logo and favicon with ```--logo``` and ```--favicon```. We export the docs to the docs subfolder with ```-o```.

### 9. Commit and push

Commit and push the updated docs to the docs branch.

### 10. Un-checkout docs branch

Continue development only after having un-checked out of the docs branch.

### Multi-line commands

You can re-run pdoc by copying and pasting the following lines together (steps 2 and 5–8), making sure to replace the absolute paths with those of the repo on your own machine:

```
cd C:\butterfly_registrator
conda activate ./env_docs
cd butterfly_registrator
set PYTHONPATH=.
pdoc C:\butterfly_registrator\butterfly_registrator -t ../docs/_templates --docformat google --logo https://olive-groves.github.io/butterfly_registrator/images/registrator_logo.png --logo-link https://olive-groves.github.io/butterfly_registrator/ --favicon https://olive-groves.github.io/butterfly_registrator/images/registrator_logo.png -o ../docs
```

## Updating packages in `environment.yml` 

If you change the environment in order to an fix issue, add a feature, or simply reduce a dependency, you can update the packages in the `environment.yml` of the root by exporting the new environment while it is activated and then replacing that existing YML in the root:

```
conda activate NAME_OF_ENV

conda install/remove PACKAGE_1
conda install/remove PACKAGE_2
...
conda install/remove PACKAGE_N

conda env export > environment.yml
```

> Take care to update both `environment.yml` and `environment_docs.yml` in the branch `docs`. If unable to do so, please create a GitHub issue requesting it be updated. 

# Credits

Butterfly Registrator is by Lars Maxfield.

Butterfly Registrator uses elements of [@tpgit<sup>↗</sup>](https://github.com/tpgit)'s *PyQt MDI Image Viewer* (with changes made), which is made available under the Creative Commons Attribution 3.0 license.

# License
<!--- If you're not sure which open license to use see https://choosealicense.com/--->

Butterfly Registrator is made available under the [GNU GPL v3.0<sup>↗</sup>](https://www.gnu.org/licenses/gpl-3.0.en.html) license or later. For the full-text, see the `LICENSE.txt` file in the root directory of the Registrator's GitHub [repo<sup>↗</sup>](https://github.com/olive-groves/butterfly_registrator).