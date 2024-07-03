# Addon template
This is a boilerplate git repository for creating new ayon addons.

## Folder structure
All addons must have server code which is located in `server` subfolder. Server side addon definition is entrypoint for each addon. Can define settings, frontend, custom endpoints, etc. Root by default contains `create_package.py` which is a helper script that prepares package structure for server. The script may be modified or expanded by needs of addon (e.g. when frontend needs to be build first). File with `version.py` is kept at the root and is copied to server and client code with script -> The reason is to make sure both parts contain same version.

### Server content
Default base of server addon is `__init__.py` file in root of repository which define addon for server. Most of addons have settings that's why `settings.py` is by default in the structure. Settings can be changed to folder/module when more than one file is needed.

### Server frontend
Addons may have their frontend. By default, server looks into `/frontend/dist` for `index.html` and addon have to have specified scopes where the frontend should be showed (check documentation of `frontend_scopes` on server addon implementation for more information).

### Private server files
Root of addon may contain subfolder `private` where can be added files that are accessible via ayon server. Url schema is `{server url}/addons/{addon name}/{addon_version}/private/*`. By default it is place where client zip file is created (during package creation). The endpoint requires authorized user.

### Public server files
Public files works the same as private files but does not require authorized user. Subfolder name is `public`. Url schema is `{server url}/addons/{addon name}/{addon_version}/public/*`. Endpoint is helpful for images/icons or other static content.

### Client content
Addons that have code for desktop client application should create subfolder `client` where a client content is located. It is expected the directory has only one file or folder in it which is named the way how should be imported on a client side (e.g. `ayon_core`).


### Example strucutre
```
├─ server
│ ├─ __init__.py
│ └─ settings.py
│
├─ frontend
│ └─ dist
│  └─ index.html
│
├─ public
│ └─ my_icon.png
│
├─ private
│ └─ kittens.png
│
├─ client
│ ├─ ayon_core
│ │ ├─ pipeline
│ │ ├─ lib
│ │ └─ ...
│ └─ pyproject.toml
│
├─ create_package.py
├─ LICENSE
├─ package.py
└─ README.md
```
