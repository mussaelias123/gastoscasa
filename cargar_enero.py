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
post({'fecha':'2026-01-01','descripcion':'Sueldo','persona':'elias','moneda':'ars','tipo':'ingreso','monto':4409460,'categoria':'Sueldo'})
post({'fecha':'2026-01-01','descripcion':'Sueldo','persona':'mari','moneda':'ars','tipo':'ingreso','monto':2299427,'categoria':'Sueldo'})

# FIJOS ELIAS ARS
post({'fecha':'2026-01-01','descripcion':'Alquiler','persona':'elias','moneda':'ars','tipo':'gasto','monto':440000,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'EPEC','persona':'elias','moneda':'ars','tipo':'gasto','monto':62084,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Ecogas','persona':'elias','moneda':'ars','tipo':'gasto','monto':5413.26,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Personal','persona':'elias','moneda':'ars','tipo':'gasto','monto':92683.21,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Seguro Auto','persona':'elias','moneda':'ars','tipo':'gasto','monto':78970,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Google','persona':'elias','moneda':'ars','tipo':'gasto','monto':2670.35,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Youtube','persona':'elias','moneda':'ars','tipo':'gasto','monto':1479,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Netflix','persona':'elias','moneda':'ars','tipo':'gasto','monto':4283,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Agua y Cloacas','persona':'elias','moneda':'ars','tipo':'gasto','monto':5000,'categoria':'Fijo'})

# FIJOS ELIAS USD
post({'fecha':'2026-01-01','descripcion':'Google','persona':'elias','moneda':'usd','tipo':'gasto','monto':2.49,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Youtube','persona':'elias','moneda':'usd','tipo':'gasto','monto':4.70,'categoria':'Fijo'})
post({'fecha':'2026-01-01','descripcion':'Netflix','persona':'elias','moneda':'usd','tipo':'gasto','monto':14.12,'categoria':'Fijo'})

# GASTOS ELIAS ARS - primera quincena
post({'fecha':'2026-01-05','descripcion':'Santa Rita','persona':'elias','moneda':'ars','tipo':'gasto','monto':5280,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Santa Rita','persona':'elias','moneda':'ars','tipo':'gasto','monto':10700,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Balance','persona':'elias','moneda':'ars','tipo':'cambio','monto':2000000,'persona_final':'mari','moneda_final':'ars','monto_final':2000000})
post({'fecha':'2026-01-15','descripcion':'Pulido luces del auto','persona':'elias','moneda':'ars','tipo':'gasto','monto':43000,'categoria':'Transporte'})
post({'fecha':'2026-01-15','descripcion':'Instalacion Aire acondicionado','persona':'elias','moneda':'ars','tipo':'gasto','monto':250000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Compra USD para terreno','persona':'elias','moneda':'ars','tipo':'gasto','monto':1490000,'categoria':'Cambio'})
post({'fecha':'2026-01-15','descripcion':'Comida Santa Rita','persona':'elias','moneda':'ars','tipo':'gasto','monto':26600,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'La Rustica','persona':'elias','moneda':'ars','tipo':'gasto','monto':50000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Ferreteria','persona':'elias','moneda':'ars','tipo':'gasto','monto':57000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Mudanza','persona':'elias','moneda':'ars','tipo':'gasto','monto':540000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Mats','persona':'elias','moneda':'ars','tipo':'gasto','monto':132146,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Pizza Bemba','persona':'elias','moneda':'ars','tipo':'gasto','monto':41500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Coworking','persona':'elias','moneda':'ars','tipo':'gasto','monto':13000,'categoria':'Servicios'})
post({'fecha':'2026-01-15','descripcion':'Deliverys','persona':'elias','moneda':'ars','tipo':'gasto','monto':37500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Proveeduria','persona':'elias','moneda':'ars','tipo':'gasto','monto':24800,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Trix','persona':'elias','moneda':'ars','tipo':'gasto','monto':25000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Eddie Burguers','persona':'elias','moneda':'ars','tipo':'gasto','monto':24800,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Coworking','persona':'elias','moneda':'ars','tipo':'gasto','monto':13000,'categoria':'Servicios'})
post({'fecha':'2026-01-15','descripcion':'Agua','persona':'elias','moneda':'ars','tipo':'gasto','monto':5800,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Carrete manguera','persona':'elias','moneda':'ars','tipo':'gasto','monto':60000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Freshy','persona':'elias','moneda':'ars','tipo':'gasto','monto':25000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Coworking','persona':'elias','moneda':'ars','tipo':'gasto','monto':13000,'categoria':'Servicios'})
post({'fecha':'2026-01-15','descripcion':'Pintura Fermin','persona':'elias','moneda':'ars','tipo':'gasto','monto':325000,'categoria':'Hogar'})

# GASTOS ELIAS ARS - segunda quincena
post({'fecha':'2026-01-25','descripcion':'Desayuno','persona':'elias','moneda':'ars','tipo':'gasto','monto':11500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Ferreteria portalamparas','persona':'elias','moneda':'ars','tipo':'gasto','monto':8200,'categoria':'Hogar'})
post({'fecha':'2026-01-25','descripcion':'Ferreteria tornillos fisher','persona':'elias','moneda':'ars','tipo':'gasto','monto':5000,'categoria':'Hogar'})
post({'fecha':'2026-01-25','descripcion':'Pizza New York','persona':'elias','moneda':'ars','tipo':'gasto','monto':34000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'El molino','persona':'elias','moneda':'ars','tipo':'gasto','monto':6500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Nafta','persona':'elias','moneda':'ars','tipo':'gasto','monto':40000,'categoria':'Transporte'})
post({'fecha':'2026-01-25','descripcion':'Santa Rita','persona':'elias','moneda':'ars','tipo':'gasto','monto':20100,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Freshy','persona':'elias','moneda':'ars','tipo':'gasto','monto':27000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Parilla','persona':'elias','moneda':'ars','tipo':'gasto','monto':106500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Zampa','persona':'elias','moneda':'ars','tipo':'gasto','monto':15500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Panaderia','persona':'elias','moneda':'ars','tipo':'gasto','monto':14500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Torta','persona':'elias','moneda':'ars','tipo':'gasto','monto':26500,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Carbon y salame','persona':'elias','moneda':'ars','tipo':'gasto','monto':12800,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Penas','persona':'elias','moneda':'ars','tipo':'gasto','monto':20500,'categoria':'Entretenimiento'})

# GASTOS MARI ARS - primera quincena
post({'fecha':'2026-01-01','descripcion':'Ano nuevo choris y tablas','persona':'mari','moneda':'ars','tipo':'gasto','monto':127811,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Acondicionador de Aire pardo','persona':'mari','moneda':'ars','tipo':'gasto','monto':792000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Mercado libre','persona':'mari','moneda':'ars','tipo':'gasto','monto':294162,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Pizzeria popular','persona':'mari','moneda':'ars','tipo':'gasto','monto':40800,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Extraccion efectivo pago Pedraza','persona':'mari','moneda':'ars','tipo':'gasto','monto':1500000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Tressen almuerzo','persona':'mari','moneda':'ars','tipo':'gasto','monto':44000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Vea','persona':'mari','moneda':'ars','tipo':'gasto','monto':168931,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Helado','persona':'mari','moneda':'ars','tipo':'gasto','monto':25800,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':28000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Shell hielo y agua','persona':'mari','moneda':'ars','tipo':'gasto','monto':9000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Limpieza casa Trix','persona':'mari','moneda':'ars','tipo':'gasto','monto':15000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Coseguro Natal','persona':'mari','moneda':'ars','tipo':'gasto','monto':8000,'categoria':'Salud'})
post({'fecha':'2026-01-15','descripcion':'Ferreteria','persona':'mari','moneda':'ars','tipo':'gasto','monto':9840,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Deliverys','persona':'mari','moneda':'ars','tipo':'gasto','monto':8300,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Proveeduria','persona':'mari','moneda':'ars','tipo':'gasto','monto':17700,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Verduleria','persona':'mari','moneda':'ars','tipo':'gasto','monto':12332,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Farmacia','persona':'mari','moneda':'ars','tipo':'gasto','monto':500,'categoria':'Salud'})
post({'fecha':'2026-01-15','descripcion':'Pizza New York','persona':'mari','moneda':'ars','tipo':'gasto','monto':19000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'El molino','persona':'mari','moneda':'ars','tipo':'gasto','monto':8100,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Santa Rita','persona':'mari','moneda':'ars','tipo':'gasto','monto':13215,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Kiosco Mauricio Gaston Aquino','persona':'mari','moneda':'ars','tipo':'gasto','monto':31000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Nutrite','persona':'mari','moneda':'ars','tipo':'gasto','monto':7550,'categoria':'Salud'})
post({'fecha':'2026-01-15','descripcion':'Mercado libre','persona':'mari','moneda':'ars','tipo':'gasto','monto':67398,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Bloom plantas','persona':'mari','moneda':'ars','tipo':'gasto','monto':118000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Mercado libre','persona':'mari','moneda':'ars','tipo':'gasto','monto':227843,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Helado','persona':'mari','moneda':'ars','tipo':'gasto','monto':25700,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':24000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Vea','persona':'mari','moneda':'ars','tipo':'gasto','monto':160799,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Lomiteria popular','persona':'mari','moneda':'ars','tipo':'gasto','monto':37600,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Instalacion Aire acondicionado','persona':'mari','moneda':'ars','tipo':'gasto','monto':420000,'categoria':'Hogar'})
post({'fecha':'2026-01-15','descripcion':'Proveeduria','persona':'mari','moneda':'ars','tipo':'gasto','monto':30400,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Mauro Borris','persona':'mari','moneda':'ars','tipo':'gasto','monto':10700,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-15','descripcion':'Santa Rita','persona':'mari','moneda':'ars','tipo':'gasto','monto':15000,'categoria':'Comida y bebida'})

# GASTOS MARI ARS - segunda quincena
post({'fecha':'2026-01-25','descripcion':'Desayuno','persona':'mari','moneda':'ars','tipo':'gasto','monto':2000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Freshy','persona':'mari','moneda':'ars','tipo':'gasto','monto':23000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Torta','persona':'mari','moneda':'ars','tipo':'gasto','monto':52000,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Cumpleanos carniceria','persona':'mari','moneda':'ars','tipo':'gasto','monto':124200,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Verduleria','persona':'mari','moneda':'ars','tipo':'gasto','monto':19250,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Hipper','persona':'mari','moneda':'ars','tipo':'gasto','monto':148801,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Mr. Dog','persona':'mari','moneda':'ars','tipo':'gasto','monto':33550,'categoria':'Hogar'})
post({'fecha':'2026-01-25','descripcion':'Autoservicio Adonai','persona':'mari','moneda':'ars','tipo':'gasto','monto':30957,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Farmaplus','persona':'mari','moneda':'ars','tipo':'gasto','monto':30607,'categoria':'Salud'})
post({'fecha':'2026-01-25','descripcion':'Mercado libre','persona':'mari','moneda':'ars','tipo':'gasto','monto':64253,'categoria':'Hogar'})
post({'fecha':'2026-01-25','descripcion':'Vea','persona':'mari','moneda':'ars','tipo':'gasto','monto':105123,'categoria':'Comida y bebida'})
post({'fecha':'2026-01-25','descripcion':'Laboratorio Lapac','persona':'mari','moneda':'ars','tipo':'gasto','monto':7000,'categoria':'Salud'})

print("Listo!")
