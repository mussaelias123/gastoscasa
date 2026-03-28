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
post({'fecha':'2026-03-01','descripcion':'Sueldo','persona':'elias','moneda':'ars','tipo':'ingreso','monto':4861301.60,'categoria':'Sueldo'})
post({'fecha':'2026-03-01','descripcion':'Sueldo','persona':'mari','moneda':'ars','tipo':'ingreso','monto':2437747,'categoria':'Sueldo'})

# FIJOS ELIAS ARS
post({'fecha':'2026-03-01','descripcion':'Alquiler','persona':'elias','moneda':'ars','tipo':'gasto','monto':1000000,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'EPEC','persona':'elias','moneda':'ars','tipo':'gasto','monto':125571.70,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'Ecogas','persona':'elias','moneda':'ars','tipo':'gasto','monto':5024.47,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'Personal','persona':'elias','moneda':'ars','tipo':'gasto','monto':30001.50,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'Seguro Auto','persona':'elias','moneda':'ars','tipo':'gasto','monto':42847,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'Google','persona':'elias','moneda':'ars','tipo':'gasto','monto':827,'categoria':'Fijo'})

# FIJOS USD ELIAS (Terreno 10/18 skip — ID 30 ya en DB con monto=0)
post({'fecha':'2026-03-01','descripcion':'Google','persona':'elias','moneda':'usd','tipo':'gasto','monto':2.49,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'Youtube','persona':'elias','moneda':'usd','tipo':'gasto','monto':4.90,'categoria':'Fijo'})
post({'fecha':'2026-03-01','descripcion':'Netflix','persona':'elias','moneda':'usd','tipo':'gasto','monto':14.62,'categoria':'Fijo'})

# GASTOS ELIAS ARS
post({'fecha':'2026-03-15','descripcion':'Freshy','persona':'elias','moneda':'ars','tipo':'gasto','monto':30500,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Nafta','persona':'elias','moneda':'ars','tipo':'gasto','monto':35000,'categoria':'Transporte'})
post({'fecha':'2026-03-15','descripcion':'Puebla','persona':'elias','moneda':'ars','tipo':'gasto','monto':89540,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Dalas y kiosco','persona':'elias','moneda':'ars','tipo':'gasto','monto':31400,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Marzolla','persona':'elias','moneda':'ars','tipo':'gasto','monto':20240,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Maridaje con Formia y Belu','persona':'elias','moneda':'ars','tipo':'gasto','monto':63900,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Maridaje','persona':'elias','moneda':'ars','tipo':'gasto','monto':47000,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Comida Nala','persona':'elias','moneda':'ars','tipo':'gasto','monto':36300,'categoria':'Hogar'})
post({'fecha':'2026-03-15','descripcion':'Verduleria','persona':'elias','moneda':'ars','tipo':'gasto','monto':22719,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-25','descripcion':'Freshy','persona':'elias','moneda':'ars','tipo':'gasto','monto':30500,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-25','descripcion':'Mercadito de sabores','persona':'elias','moneda':'ars','tipo':'gasto','monto':18800,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-25','descripcion':'Tijera podadora','persona':'elias','moneda':'ars','tipo':'gasto','monto':8372,'categoria':'Hogar'})
post({'fecha':'2026-03-25','descripcion':'Kiosco','persona':'elias','moneda':'ars','tipo':'gasto','monto':9100,'categoria':'Comida y bebida'})

# GASTOS MARI ARS
post({'fecha':'2026-03-15','descripcion':'Chef Mauro Borris','persona':'mari','moneda':'ars','tipo':'gasto','monto':16500,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Adonai','persona':'mari','moneda':'ars','tipo':'gasto','monto':8955,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Casa verde','persona':'mari','moneda':'ars','tipo':'gasto','monto':27400,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Almuerzo Mussa','persona':'mari','moneda':'ars','tipo':'gasto','monto':20000,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Coseguros','persona':'mari','moneda':'ars','tipo':'gasto','monto':8000,'categoria':'Salud'})
post({'fecha':'2026-03-15','descripcion':'Lo de Jacinto','persona':'mari','moneda':'ars','tipo':'gasto','monto':22900,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Picca','persona':'mari','moneda':'ars','tipo':'gasto','monto':36400,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Proveeduria','persona':'mari','moneda':'ars','tipo':'gasto','monto':11300,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Farmacia','persona':'mari','moneda':'ars','tipo':'gasto','monto':12596,'categoria':'Salud'})
post({'fecha':'2026-03-15','descripcion':'Vea','persona':'mari','moneda':'ars','tipo':'gasto','monto':152922,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Mercado libre','persona':'mari','moneda':'ars','tipo':'gasto','monto':353938,'categoria':'Hogar'})
post({'fecha':'2026-03-15','descripcion':'Ferreteria','persona':'mari','moneda':'ars','tipo':'gasto','monto':25300,'categoria':'Hogar'})
post({'fecha':'2026-03-15','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':58000,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'La coope hipper','persona':'mari','moneda':'ars','tipo':'gasto','monto':229858,'categoria':'Comida y bebida'})
post({'fecha':'2026-03-15','descripcion':'Maridaje con Formia y Belu','persona':'mari','moneda':'ars','tipo':'gasto','monto':5000,'categoria':'Comida y bebida'})

print("Listo!")
