import urllib.request, urllib.parse, json

BASE = 'http://localhost:5000'

def post(data):
    d = {k: str(v) for k, v in data.items()}
    req = urllib.request.Request(
        f'{BASE}/agregar',
        data=urllib.parse.urlencode(d).encode(),
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    r = json.loads(urllib.request.urlopen(req).read())
    if not r.get('ok'):
        print(f'ERROR: {data}')
    return r

# SUELDOS
post({'fecha':'2026-02-01','descripcion':'Sueldo','persona':'elias','moneda':'ars','tipo':'ingreso','monto':5463740,'categoria':'Sueldo'})
post({'fecha':'2026-02-01','descripcion':'Sueldo','persona':'mari','moneda':'ars','tipo':'ingreso','monto':2207230,'categoria':'Sueldo'})

# FIJOS ELIAS ARS
# Nota: Agua y Cloacas (46758) omitida — formula muerta en Excel de feb, no afecta saldo final
post({'fecha':'2026-02-01','descripcion':'EPEC','persona':'elias','moneda':'ars','tipo':'gasto','monto':80557.70,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'Ecogas','persona':'elias','moneda':'ars','tipo':'gasto','monto':2274,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'Seguro Auto','persona':'elias','moneda':'ars','tipo':'gasto','monto':42487,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'Youtube','persona':'elias','moneda':'ars','tipo':'gasto','monto':1427.80,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'HBO Max','persona':'elias','moneda':'ars','tipo':'gasto','monto':1792,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'Netflix','persona':'elias','moneda':'ars','tipo':'gasto','monto':4283.60,'categoria':'Fijo'})
# Terreno 9/18 es en ARS este mes (no estaba pre-cargado en DB)
post({'fecha':'2026-02-01','descripcion':'Terreno Costa Jardin','persona':'elias','moneda':'ars','tipo':'gasto','monto':1470000,'categoria':'Fijo'})

# FIJOS USD ELIAS
post({'fecha':'2026-02-01','descripcion':'Youtube','persona':'elias','moneda':'usd','tipo':'gasto','monto':4.89,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'HBO Max','persona':'elias','moneda':'usd','tipo':'gasto','monto':6.00,'categoria':'Fijo'})
post({'fecha':'2026-02-01','descripcion':'Netflix','persona':'elias','moneda':'usd','tipo':'gasto','monto':14.23,'categoria':'Fijo'})

# Compra USD (cambio ARS→USD, este mes Terreno es ARS asi que el USD ingresa limpio)
post({'fecha':'2026-02-15','descripcion':'Compra USD','persona':'elias','moneda':'ars','tipo':'cambio','monto':1500000,'persona_final':'elias','moneda_final':'usd','monto_final':1060.07})

# GASTOS ELIAS ARS
post({'fecha':'2026-02-15','descripcion':'Kiosco','persona':'elias','moneda':'ars','tipo':'gasto','monto':24300,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Penas','persona':'elias','moneda':'ars','tipo':'gasto','monto':8000,'categoria':'Entretenimiento'})
post({'fecha':'2026-02-15','descripcion':'Santa Rita','persona':'elias','moneda':'ars','tipo':'gasto','monto':8230,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Vita Bona','persona':'elias','moneda':'ars','tipo':'gasto','monto':14900,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'New York con Patri Iara y plata delivery','persona':'elias','moneda':'ars','tipo':'gasto','monto':72000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Nutridiet','persona':'elias','moneda':'ars','tipo':'gasto','monto':56700,'categoria':'Salud'})
post({'fecha':'2026-02-15','descripcion':'Coworking','persona':'elias','moneda':'ars','tipo':'gasto','monto':14000,'categoria':'Servicios'})
post({'fecha':'2026-02-15','descripcion':'Eddie Burger','persona':'elias','moneda':'ars','tipo':'gasto','monto':26300,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Santa Rita','persona':'elias','moneda':'ars','tipo':'gasto','monto':13860,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Winston','persona':'elias','moneda':'ars','tipo':'gasto','monto':106000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'El Molino','persona':'elias','moneda':'ars','tipo':'gasto','monto':6700,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Milanesas','persona':'elias','moneda':'ars','tipo':'gasto','monto':13600,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Brancato','persona':'elias','moneda':'ars','tipo':'gasto','monto':16000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Nafta','persona':'elias','moneda':'ars','tipo':'gasto','monto':30000,'categoria':'Transporte'})
post({'fecha':'2026-02-15','descripcion':'Desayuno YPF','persona':'elias','moneda':'ars','tipo':'gasto','monto':23400,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'El club de la Milanesa','persona':'elias','moneda':'ars','tipo':'gasto','monto':40958,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Heladito McDonald','persona':'elias','moneda':'ars','tipo':'gasto','monto':5500,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Estacionamiento Patio Olmos','persona':'elias','moneda':'ars','tipo':'gasto','monto':11000,'categoria':'Transporte'})
post({'fecha':'2026-02-15','descripcion':'Kiosco Adonai pastas','persona':'elias','moneda':'ars','tipo':'gasto','monto':24312,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'La Rustica','persona':'elias','moneda':'ars','tipo':'gasto','monto':28000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Lavanderia','persona':'elias','moneda':'ars','tipo':'gasto','monto':95000,'categoria':'Hogar'})
post({'fecha':'2026-02-25','descripcion':'Rincon de las delicias','persona':'elias','moneda':'ars','tipo':'gasto','monto':48481,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Pizza Mia','persona':'elias','moneda':'ars','tipo':'gasto','monto':15800,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Casamiento Diane','persona':'elias','moneda':'ars','tipo':'gasto','monto':194000,'categoria':'Entretenimiento'})
post({'fecha':'2026-02-25','descripcion':'Freshy','persona':'elias','moneda':'ars','tipo':'gasto','monto':33500,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Ribera Pampa','persona':'elias','moneda':'ars','tipo':'gasto','monto':62000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Eddie Burgers','persona':'elias','moneda':'ars','tipo':'gasto','monto':26800,'categoria':'Comida y bebida'})

# GASTOS MARI ARS
post({'fecha':'2026-02-01','descripcion':'Cuota Carestino 1/6','persona':'mari','moneda':'ars','tipo':'gasto','monto':202298.70,'categoria':'Hogar'})
post({'fecha':'2026-02-15','descripcion':'Pileta','persona':'mari','moneda':'ars','tipo':'gasto','monto':163900,'categoria':'Hogar'})
post({'fecha':'2026-02-15','descripcion':'Shein','persona':'mari','moneda':'ars','tipo':'gasto','monto':408794,'categoria':'Ropa'})
post({'fecha':'2026-02-15','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':26000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':30000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Lacteos premium','persona':'mari','moneda':'ars','tipo':'gasto','monto':17466,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Don Bartolo','persona':'mari','moneda':'ars','tipo':'gasto','monto':38600,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Vea','persona':'mari','moneda':'ars','tipo':'gasto','monto':158181,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Panaderia buen dia','persona':'mari','moneda':'ars','tipo':'gasto','monto':15398,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Helado','persona':'mari','moneda':'ars','tipo':'gasto','monto':26200,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Kiosco adonai','persona':'mari','moneda':'ars','tipo':'gasto','monto':22783,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Ecografia','persona':'mari','moneda':'ars','tipo':'gasto','monto':83000,'categoria':'Salud'})
post({'fecha':'2026-02-15','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':25000,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Casa verde','persona':'mari','moneda':'ars','tipo':'gasto','monto':15800,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-15','descripcion':'Kiosco adonai','persona':'mari','moneda':'ars','tipo':'gasto','monto':44220,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Lomiteria popular','persona':'mari','moneda':'ars','tipo':'gasto','monto':39400,'categoria':'Comida y bebida'})
post({'fecha':'2026-02-25','descripcion':'Helado','persona':'mari','moneda':'ars','tipo':'gasto','monto':26300,'categoria':'Comida y bebida'})

print("Listo!")
