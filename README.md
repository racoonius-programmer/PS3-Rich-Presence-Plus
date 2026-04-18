# PS3 Rich Presence Plus

Discord Rich Presence para PS3 con HEN/CFW y webMAN MOD.

Muestra en Discord el juego que estás usando actualmente en tu PS3 desde tu PC.

Forkeado desde el repo de [zorua98741](https://github.com/zorua98741/PS3-Rich-Presence-for-Discord).

## Cambios

- Cambia `networkscan` por `concurrent.futures`.
- Añade webMAN como repositorio para buscar imágenes de los juegos.
- Añade expresiones regulares para limpiar títulos de juegos cuando aparezcan con versiones en el nombre, por ejemplo `1.00`.
- Añade `show_xmb` a la configuración para alternar si se muestra el estado mientras estás en el XMB.
- Mejor detección de juegos de PS2 Classics.

## Ejemplos de Status
<table>
	<tr>
		<td>XMB</td>
		<td> <img src="https://github.com/zorua98741/PS3-Rich-Presence-for-Discord/blob/main/img/xmb.png?raw=true"> </td>
	</tr>
	<tr>
		<td>PS3</td>
		<td> <img src="https://github.com/zorua98741/PS3-Rich-Presence-for-Discord/blob/main/img/ps3.png?raw=true"> </td>
	</tr>
	<tr>
		<td>PS1/2</td>
		<td> <img src="https://github.com/zorua98741/PS3-Rich-Presence-for-Discord/blob/main/img/retro.png?raw=true"> </td>
	</tr>
</table>


## ¿Cómo usar?

### Requisitos

- PS3 con HFW y HEN, o con CFW instalado.
- PS3 con [webMAN MOD](https://github.com/aldostools/webMAN-MOD/releases) instalado.
- PS3 y PC conectados a la misma red; el script buscará la IP automáticamente.
- Discord instalado y abierto con el script en ejecución.
- Python 3.9 o superior instalado.
- Instalar las dependencias desde `requirements.txt`.

### Windows

- Clona el repositorio.
- Ejecuta `PS3RPD.pyw`.

### Opcional: iniciar al prender el PC

- Si quieres que arranque al iniciar el PC, crea un acceso directo de `PS3RPD.pyw`.
- Presiona `Win + R` y escribe `shell:startup`.
- Pega el acceso directo en esa carpeta.

## Limitaciones

- Se necesita un PC para mostrar el estado; no se puede instalar y usar este script solo en la PS3.
- El script depende de webMAN MOD, así que un cambio importante en su estructura puede romperlo.
- Los nombres de juegos de PSX y PS2 dependen del nombre del archivo.
- La detección de juegos PSX y PS2 no funcionará con versiones PSN `.pkg`, porque webMAN no puede mostrar esos juegos como montados o en ejecución.
- La detección de juegos PS2 ISO puede ser inconsistente, dependiendo del tiempo de refresco.

## Información adicional

### GameTDB + webMAN

Este script usa imágenes proporcionadas por [GameTDB](https://www.gametdb.com/) y [Aldostools / webMAN](https://raw.githubusercontent.com/aldostools/Resources). Si puedes, considera apoyar a sus autores.

### Archivo de configuración externo

PS3RPD usa un archivo de configuración externo para guardar de forma persistente algunas variables. Al crearse, los valores por defecto serán:

- La IP de tu PS3. Si no la conoces, el script la buscará automáticamente hasta encontrar una PS3 con HEN activado.
- El ID de la aplicación de Discord de `zorua98741`, donde el script enviará los datos del estado.
- Un tiempo de actualización de 45 segundos, que define cada cuánto se obtienen nuevos datos.
- Mostrar la temperatura de la PS3.
- Mostrar Rich Presence mientras estás en el XMB.
- Un tiempo de hibernación de 10 segundos, que sirve de espera antes de volver a buscar IPs.

## Notas sobre PS2 Classics

- PS2 Classics puede requerir una detección más flexible, porque webMAN no siempre muestra la misma estructura HTML.
- Si un juego de PS2 Classics no aparece en el estado, normalmente el problema está en cómo webMAN está exponiendo el nombre o la ruta del juego.
- En HEN, los PS2 ISO suelen requerir estar preparados como `.BIN.ENC` para poder ejecutarse correctamente.

## Soporte y apoyo

Este proyecto usa imágenes e información de GameTDB y webMAN MOD. Si te sirve el proyecto, considera apoyar a sus desarrolladores.