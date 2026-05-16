# I created a bot with Claude… and this happened

- video: https://youtu.be/28XJPdNmO10
- lang: es
- source: automatic_captions (сырой ASR, черновик)

---

Mira, hoy voy a hacer algo que probablemente casi nadie está haciendo todavía. Voy a usar Cloud, la
nueva inteligencia artificial, que está muy de moda, muy en tendencia, para crear un bot de trading
desde cero, sin programar, sin tocar código manualmente y viendo en tiempo realmente funciona o no.
Y quédate hasta el final porque hay algo que descubrí usando Cloud que cambia completamente cómo
deberíamos crear bots de trading con [música] inteligencia artificial. ¿Estás preparado? Pues
empecemos. Advertencia de riesgo. El treno conlleva riesgo significativo de pérdida y puede no ser
adecuado para todos los inversores. Este contenido es exclusivamente informativo y no constituye
asesoramiento financiero ni recomendación de inversión. Los rendimientos pasados no garantizan
resultados en el futuro. Si has intentado crear un bot trading con IA, seguramente te ha pasado
esto. Le pides a la IA una estrategia, te devuelve algo que suena bien, pero cuando intentas usarlo
no sabes si sirve o no. o peor, te da código, pero sabe si está bien hecho. Y aquí está el problema
real. La mayoría de gente usa mal la inteligencia artificial porque no es solo pedir hazme un bot,
es saber cómo pedirlo, qué prom utilizar exactamente. Aquí es donde Cloud nos puede ayudar porque a
diferencia de otras Ias, Cloud es mucho mejor estructurando lógica compleja y código. Así que en
este vídeo voy a hacer esto. Le voy a pedir una estrategia. Le voy a pedir que la convierta en un
bot. Le voy a llevar pues este código a Metatrader 5 y vamos a hacer un back test durante 5 años del
pasado para comprobar su rendimiento. Mira, lo mejor que podemos hacer es ir al ordenador y hacer
todo esto en la práctica. Vale, estamos aquí dentro de cloud para poder seguir los mismos pasos.
Vais a cloud.i y es posible que tengáis que iniciar sesión al menos para que os quede un histórico
de el uso que habéis hecho de cloud. Entonces, con una cuenta de correo tipo Gmail, pues es
suficiente. Yo, si os fijáis, estoy en el plan gratuito. Ah, eh, por lo tanto, no tengo ah lo que es
Cloud código, pero vamos a usar la versión gratuita y veréis cómo se puede hacer pues lo mismo
prácticamente que en la de código que ya está más especializada en código. En vez de hacerlo típico,
voy a usar un prom estructurado. Esto es clave. y le he escrito esto que veis a continuación. Quiero
que actúes como un experto en trading algorítmico. Creó una estrategia de trading basada en
indicadores técnicos clara con reglas de entrada, salida, gestión de riesgo y time frame, con
lenguaje de programación MQL5 para Metatrader 5. Pregúntame lo que necesitas para acabar de definir
la estrategia, mercado, temporalidad, etcétera. Y eh como tengo la versión gratuita, pues tampoco
tengo acceso a 4.7, que es la última versión. Estoy todo con el plan gratuito porque sí que a veces
me decís que no os funciona igual y puede ser pues por ejemplo en chat GPT que estoy en una versión
de pago y [carraspeo] después cuando vosotros seguís los pasos pues os encontráis con que no sale lo
mismo. Vale, perfecto. Con toda esta información ya puedo construir la estrategia completa. Dime tus
respuestas a estos a estas dos tandas de preguntas y me pongo manas a la obra con el código. ¿En qué
mercado quieres operar? [carraspeo] Forex. Índices, criptomonedas, materias primas. Pues Forex. ¿Qué
temporalidad prefieres? Pues scalping no. Nos vamos a intradía, pero ya en temporalidades no
[carraspeo] tan bajas como M1 o M5. ¿Qué estilo de estrategia te interesa? Tendencia, revisión a la
media, ruptura de niveles, combinación de señales múltiples. Pues hago la cuarto combinación de
señales múltiples, de tal manera que es lo que hacemos normalmente, donde trabajamos con más de un
indicador y cuando se alínean un par de ellos es cuando entramos, ¿no? Generalmente hacemos uno de
tendencia y uno que es el gatillo de entrada. Aparte de cloud, que en cloud.i pues podéis usar la
IA, estoy en la versión gratuita. También usaremos Metatrader y ahora os explicaré cómo. Seguimos
con las preguntas. Voy a ponerme por aquí arriba. ¿Qué riesgo máximo por operación quieres asumir?
Pues le digo 1%. ¿En qué dirección quieres operar? ¿Solo largos? ¿Solo cortos? Ambas direcciones.
¿Cómo prefieres gestionar el trade profit? Si quiero un trailing stop, no stop loss ITP fijos trade
profit parcial más trailing, pues hago stoppijos. Entonces, perfecto, ya tengo todo lo que necesito.
Voy a construir un EA [carraspeo] completo. Y realmente Cloud es muy interesante su funcionamiento.
Es distinta a Chat GPT o Gemini, que son más parecidas. Cloud tiene ventajas respecto a otras. Ya en
un futuro haré un vídeo más tipo comparativa. Lógica de la estrategia, un cruce de medias filtra la
tendencia MA50, MA2. Eso después se podrá optimizar y buscar qué más son las más interesantes de
utilizar a nivel de [carraspeo] de beneficio. El RSI filtra el momentum, evita zonas extremas, el
[resoplido] MACD, una señal de entrada, cruce de líneas y ATR para stop loss y TP dinámicos adaptado
a la volatilidad. Gestión de riesgo, tamaño de lote calculado automáticamente al 1% del balance. Es
una estrategia potente. En realidad es una estrategia de tres indicadores. El tema del ATR ayuda
simplemente a las distancias de stopp y está redactando. Mientras tanto, ¿qué otro programa
necesitamos? Metatrader es gratuito y abrir una cuenta demo también es gratuito. ¿Cómo se hace? Pues
vais a metatrader 5.com, descargáis la versión para Windows, Mac o Linux, no sirve para terminal o
para iPhones, o sea, para smartphones. Ah, tiene que ser de terminal, si no no podréis hacer lo
mismo. Una vez descargado Metatrader, aquí ya vemos que está trabajando, ah, tendréis este software,
importante, loguearos en una cuenta o abrir una cuenta. Entonces, aquí en metacuotes, dais el
siguiente y después ya os dice para crear una demo, os pide los datos y ya tendréis una demo.
Fijaros que tengo metacuotes demo y aquí el número de cuenta de esta demo. Aquí está trabajando y a
veces distinto a lo que estáis acostumbrado. Ah, las maneje de forma independiente. Bueno, esto es
para instalar programas. Filtro horario, ¿no? Filtro de tendencia. Filtro de momentum. Señal de
entrada. Bueno, te hace todo un organigrama. Está muy bien, está muy bien Cloud, por eso se está
últimamente hablando mucho de él, porque además con los las versiones nuevas que han salido, pues es
muy potente, ¿eh? Entonces parece que ya lo tenemos. Autor generado con Cloud de Antropic para Forex
Temporalidad M15H1. Entonces, ¿qué tenemos que hacer ahora? Copiar el código y nos vamos a
Metatrader. Dentro de Metatrader donde pone IDE, Metatrader 5, eh, que es el editor de metacuotes
lenguajes, la parte donde se introducen bots. Pulsamos en nuevo, asesor experto. Aquí le decimos
cloud y pues el día que lo he hecho, el día que grabo el vídeo, cloud 246 [carraspeo] siguiente.
Siguiente. Finalizar. Borro todo lo que pone, dejo la pizarra en blanco y pego aquí el código. Son
289 líneas, no hay errores ni warnings. Bueno, para cloud. Salgo de ahí para que te salga en ya
Metatrader, porque el metacuotes ya lo he cerrado. Vas a ver navegador y donde pone asesores
expertos es donde están los bots. Actualizas. Una vez actualizado, aquí tenemos cloud 24 del 4 del
26. Si arrastro en un gráfico, ya tenemos aquí pues [carraspeo] toda la configuración por si lo
queremos poner en una cuenta demo, que es todo lo que veis aquí en pantalla. ¿Qué nos dice?
[carraspeo] Símbolo el actual, si está vacío hará pues libradólar M15 tengo yo aquí. Si no, pues
podemos rellenar aquí donde queremos que opere. [carraspeo] Temporalidad H1 o M15, el cruce de Emas
RSI sobrepra de sobrecompra sobre venta, el MACD es más rápida y más lenta y la señal. Eh, periodos
de ATR, distancia de stop ITP, riesgo por operación, mas number, sleepage, máximo de operaciones
simultáneas, está puesto solo una. Si queremos un filtro horario que solo opera de 7 a 8, pues está
puesto en true. Bueno, si ahora pongo aceptar, ya está aquí funcionando. Si me veis, sale el birrete
gris. Si activo el trading automático, pues ya se debería poner. Como no se ha puesto aún, eso es
porque tenemos que ir a herramientas opciones y sobre todo que esté permitir trading automático
activo. Entonces, lo que vamos a hacer ahora, ¿vale? Ya sé por qué sale el virrete así, porque no
estamos dentro de la franja horaria, voy a hacer una pequeña prueba rápida. Volvemos a la letra C de
Cloud, arrastramos en el gráfico y si yo le digo que siempre opere, no haya filtro horario, ya se
nos pone azul. Perfecto, es lo que me imaginaba. Ahora vamos ya al probador porque aquí nos
[carraspeo] aburriríamos mucho. Y aquí tenemos que hacer un primer back test. Vamos a back testico,
seleccionamos el bot que acabamos de crear, que es este de aquí, eh, libradó H1, por ejemplo, y le
pongo, pues los últimos 5 años, del año 21 al 26. El 26 no está incluido, que estamos ahora mismo en
el año 26 y está a medias. Y pues solo precios de apertura para que el vídeo vaya fluido. Cuenta de
10,000 y le quito el filtro horario. Bueno, de momento pongo todo tal como lo ha hecho. Está por
defecto, por curiosidad, a ver si ha sido capaz de de ganar o no. Pues de momento no ha tomado
operaciones. Pongo el filtro horario en false. Empezar tampoco. E bueno, cuando no os opera un bot,
¿qué [carraspeo] podemos hacer? Optimizar. Al optimizar, [tos] disculpas. [carraspeo] Al optimizar
lo que hacemos es pues mirar si es que los parámetros eran muy exigentes. Por ejemplo, la EMA es un
punto a optimizar, el símbolo no. La EMA los marco y le digo pues que la EMA lenta vaya de cinco
saltos de cinco en cinco hasta llegar a 50. No voy a subir a 100. Y la Ema rápida, cinco saltos de
cinco en cinco, perdón que no empiece en cinco, sino que empiece en 50, saltos de cinco en CCO hasta
llegar a 200. Periodos de RSI no los optimizo. Y lo que es el RSI, pues mira, voy a hacer una cosa
para no sobreptimizar. Esto está en 6535, no está mal. Eh, el MACD es lo que vamos a optimizar
porque no quiero hacer más de 3 grados de libertad. Optimizamos el indicador EMA, el indicador MACD
y stop ITP. Entonces me salto el RSI [carraspeo] en el MACD. Pues aquí [carraspeo] vamos saltos de
uno en uno hasta llegar a 20. Aquí hacemos unos saltos de uno en uno hasta llegar a 50. Bueno, aquí
vamos de dos en dos y la señal de MCD también uno. Saltos de uno en uno [tos][carraspeo] hasta
llegar a 50. Stop loss ITP pues 0.5 5 con saltos de 05 en 05 hasta llegar a un stop loss de 20 y lo
mismo para el take profit 05, saltos de 05 en 05 hasta llegar a 20. Entonces, vamos a ver. Salen
muchos, muchos, muchos. Y eso es por el MACD que nos dispara bastante. Entonces, mira, vamos solo a
optimizar la señal y no optimizamos pues los otros parámetros de MACD. Empezamos la optimización.
Empezará a salir una nube de puntos aquí arriba. Eh, si os fijáis a de 10,496, pues va a ir buscando
a ver si toma alguna operación, alguna combinación de parámetros. Esto tarda un poco, así que lo
paso a cámara rápida. Bien, ha terminado. No toma ninguna entrada. Entonces, ah, vamos a hacer una
última prueba, que es un escaneo de mercado donde va a probar de todas las [carraspeo][tos] en todos
los mercados que tengo si en alguno toma entradas y vemos que no. Sí, toma entradas en estos
mercados de aquí y no tome entradas en Forex, que se supone que es para Forex el símbolo actual. Si
lo pongo vacío, [carraspeo][tos] ahora podríamos ir a la IA, decirle, "Mira, no me está tomando
entradas en estos mercados. A ver si es que eh hay algún error, alguna cosa y enseguida nos lo
resolvería. Pero lo que vamos a hacer es irnos al oro, por ejemplo. Doy doble clic al oro y aquí ya
tenemos el back test en el oro que no ha ido muy bien. Y esto es un back test sin optimizar. Ahora
ya vendría la optimización, la que habíamos planteado antes, pero lo vamos a hacer en el oro. Ahí sí
que ya empiezan a salir ganadoras. Si están por aquí arriba es ganancia, si están por aquí es break
even y si salen rojas es pérdida. Así que paso esta parte a cámara rápida y vemos el resultado de lo
que es esta optimización enseguida. Perfecto, ya terminó. Y vemos que la opción con mayor beneficio
pasa de 10.000 a una locura. 3,594,427. Esto es un 35,944% eh, con 2011 operaciones en 5 años. Es de
locos, pero también el la reducción no es asumible, o sea, es desproporcionado el drawdown. Eso me
hace pensar que debe haber opciones que han quebrado la cuenta. Exacto. Por aquí ya vemos opciones,
combinaciones de parámetros peores. Por ejemplo, esta primera con un profit factor de 170. Le doy
doble clic y ya se ha hecho el back testing y eh vemos pues que es un gráfico eh que no me acaba de
atraer mucho. Entonces eh vamos a ver si por factor de beneficio encontramos alguna más interesante.
Aquí el número de operaciones es un poco bajo, así que el drawdown es más razonable. Entonces, aquí
ya tenemos 128. Le doy doble clic con un factor de beneficio muy alto, pero vemos que pasa como
antes, que casi todo el beneficio es en la parte final. Aquí 149 operaciones. Bueno, todos se acaban
pareciendo eh, para esta práctica que no me quiero alargar porque pasarían, faltarían muchos pasos.
Vamos a poner esta primera opción que es este gráfico de aquí donde pues el beneficio es de locos,
pero también la reducción es muy exagerada. Y lo que vamos a hacer es ajustar el lotaje. Para ello,
vuelvo a poner optimizar. y quito todo lo de antes. Ya no me interesa optimizar lo que habíamos
hecho antes, sino que ahora lo que me interesa simplemente es optimizar el porcentaje de riesgo por
operación. Y aquí [carraspeo] pues yo hago desde 0.1, saltos de 01 en 01 hasta llegar al 1%. Si
queremos afinar más, puedo hacer de 0.01 con saltos de 0.01 y ahí ya afinamos mucho más. Le pongo a
optimizar y esta optimización ha ido muy rápido. Entonces, importante, la reducción os da pista. Si
está en roja es que no es una reducción asumible. Si está en naranja, como pasa con el semáforo, es
un perfil de riesgo muy elevado, pero ya podría ser razonable. Y después, si está en verde, ya es
menos del 20. Fijaros que es por debajo del 30 y encima del 20 naranja. Si supera el 30 ya es un
drawdown, una pérdida en ese periodo exagerada. Cuando ya se pone verde, pues es un perfil. Yo
siempre busco esto que esté por debajo del 20. De todos modos, hemos hecho un, muevo la coma dos
posiciones, un 1272%. Le doy doble clic, es esto de aquí, un 1272% con un drawdown del 20 eh, en 5
años. Eso da una media anual, pues 1272 di 5 años da un 254% anual. Tenemos que ajustar aún más el
lotaje. Fijaros que está en 29% la reducción del equity, que es la que os tenéis que fijar.
Entonces, eh no sé por qué aquí la reducción me la pinta de una manera y después no es exacto. Por
ejemplo, con 025% por operación ya estamos en un 24. Y si me voy, por ejemplo, aquí un perfil de
riesgo ya mucho mejor a 015% estamos con un 15% de reducción de drawdown. Lo único que el beneficio
es de un 284%. Claro, cuando más conservador somos. Esto es un 56% anual que sigue siendo bestial. Y
lógicamente quedarían muchísimos pasos, pero ahora no quiero alargarme más. Este vídeo era para
tener ese contacto con Cloud, ver que nos ayuda a desarrollar las estrategias, que nos puede ayudar
no solo a programar, sino en muchísimas cosas. Y espero que os haya gustado. Y aquí está la
conclusión importante de la práctica de hoy. Cloud no es magia, pero bien utilizado puede ahorrarte
horas de tiempo, puede ayudarte a crear la estrategia, estructurarla, convertirla en un bot de
trading para Metatrader 5. El problema nunca ha sido la IA, es como la utilizamos. Si quieres
aprender a hacer esto bien y crear tus propios bots paso a paso con inteligencia artificial, he
preparado algo especial para ti. Es una guía gratuita donde te enseño exactamente cómo estructurar
proms para crear estrategias y bots. Lo tienes en el link de la descripción y también aquí en
pantalla en el comentario fijado donde puedes descargar ese super prom junto con la guía para crear
bots. Si te ha gustado este vídeo, no te olvides de dejar un me gusta, suscribirte al canal y
visitar la academia de Tringo en todas las formaciones código. Trading. Advertencia de riesgo. El
tren lleva riesgo significativo de pérdida y puede no ser adecuado para todos los inversores. Este
contenido es exclusivamente informativo y no constituye asesoramiento financiero ni recomendación de
inversión. Los rendimientos pasados no garantizan resultados futuros.
