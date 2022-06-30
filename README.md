# GLManager

## Modo de instalacao manual

* Instalando GIT 

```
sudo apt-get update && sudo apt-get install git -y
```

* Instalando script
```
git clone https://github.com/BXJSBSKSBDIN/GLManager.git
cd GLManager
pip3 install -r requirements.txt
```

* Execute o script
```
python3 -m app
```

## Modo de instalacao automatizada

* Instalando python3, pip3 e git
```
sudo apt-get update && sudo apt-get install git python3 python3-pip -y
``` 

* Instalando script
```
pip3 install git+https://github.com/BXJSBSKSBDIN/GLManager.git
```
#### Ou
```
git clone https://github.com/BXJSBSKSBDIN/GLManager.git
cd GLManager
python3 setup.py install
```

## Atualize o script
```
pip3 install --upgrade git+https://github.com/BXJSBSKSBDIN/GLManager.git
```
#### Ou
```
cd ~/
rm -rf GLManager
git clone git+https://github.com/BXJSBSKSBDIN/GLManager.git
cd GLManager
python3 setup.py install
```

* Comando de execucao
```
vps
```
