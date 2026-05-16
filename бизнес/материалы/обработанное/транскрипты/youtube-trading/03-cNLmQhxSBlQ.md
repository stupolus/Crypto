# Cómo Conectar Claude A TradingView Para Que Haga Trading Por Ti

- video: https://youtu.be/cNLmQhxSBlQ
- lang: es
- source: automatic_captions (сырой ASR, черновик)

---

Este vídeo es una guía completa sobre cómo conectar Cloud Code con Trading View, siguiendo solo tres
sencillos pasos sin la necesidad de saber programar o de utilizar aplicaciones complicadas. Te
guiaré paso a paso, empezando desde cero y llegando a conectar la inteligencia artificial de Cloud
con tu propio Trading View para que empieces a pedirle cosas. análisis de gráficos, creación de
indicadores personalizados, back testings automáticos de estrategias de trading, etcétera, etcétera.
Una vez visto el vídeo, empezarás a ahorrarte dinero y tiempo por el simple hecho de que la mayoría
de tareas que a día de hoy tienes que hacer tú mismo las va a empezar a hacer Cloud Code de forma
automatizada por ti. Así que, habiendo dicho esto, vamos con el primer paso. Lo primero de todo, te
recomiendo que vayas al primer comentario fijado o la descripción de este vídeo, ya que encontrarás
un pequeño enlace que te va a llevar directamente a mi canal de Telegram oficial, en el cual te he
dejado un PDF con todas las instrucciones que vamos a seguir a continuación. Así que si quieres
descargarlo gratis, simplemente tienes que ir a mi canal de Telegram y buscarlo. Antes de empezar
con el primer paso, tienes que cumplir los tres requisitos siguientes. El primero de ellos es tener
la aplicación de escritorio de Trading View. Simplemente vas a Trading View, buscas la aplicación de
escritorio y eliges el sistema operativo. La descargas y ya la tendrías. Primer requisito cumplido.
En segundo lugar, necesitas una cuenta de Cloud suscripción de pago, ya sea la Pro o ya sea la Pro
Max. La versión gratuita de Cloud no permite utilizar Cloud Code, así que tienes que pagar, por así
decirlo, uno de los planes de pago de Cloud. Yo tengo, por ejemplo, el Pro ya es suficiente, no es
necesario el Pro Max o el Max o lo que sea, ¿no? Finalmente tienes que ir al siguiente enlace que lo
vas a encontrar en el PDF o puedes poner nodejs.org para descargarte lo siguiente. Descarga la
versión LTS, que es la recomendada, e instálala como cualquier programa normal. De nuevo, elige si
es Mac o si es otro sistema y la descargas sin ningún problema. Es importante que este programa lo
tengas descargado de manera pues habitual y normal. No necesitas ni una terminal ni nada extraño. Es
como si fuera cualquier otro programa. Una vez cumples con los tres requisitos, vamos con el paso
uno y es instalar Cloud Code en el ordenador. Es decir, con la aplicación del navegador no sirve.
Necesitas la terminal, por así decirlo, de Cloud Code. Para ello, dale a, en mi caso, que tengo
MacBook, comando más espacio y escribe terminal. Una vez tienes escrito terminal, presiona enter. Ya
dentro de la terminal de tu sistema operativo tienes que ejecutar el siguiente comando y volver a
darle enter. Oye, Alex, me ha dado error. ¿Qué hago? ¿Cómo lo soluciono? Bueno, evidentemente yo no
puedo estar pendiente de todos y cada uno de los errores que puedan darse, pero fijaros qué es lo
que he hecho. Hacer captura de pantalla al error. He venido directamente a Cloud, le he preguntado
por qué no me deja instalar. Y nada, pues ya me ha explicado qué es lo que ocurre y qué es lo que
tengo que hacer. Así que lo que voy a hacer a continuación es seguir estos pasos y olvidarme de
dicho error. Así que ejecuto la primera orden que me ha indicado Cloud. Luego ejecuto y vuelvo a
instalar el comando que he mencionado al principio y ya lo tendría listo. Para verificar que está
todo pego el siguiente comando, verifico que todo está instalado y fijaros cómo me devuelve la
versión en la cual nos encontramos ahora mismo. Paso uno, solventado, tenemos cloud code en nuestro
ordenador. Paso dos en el que nos encontramos ahora mismo, lanzar Cloud Code. ¿Para qué? Pues para
poder utilizarlo como queramos. El objetivo de este vídeo concretamente es relacionar Cloud Code con
Trading View y poder ejecutar directamente. Así que a continuación vamos a desarrollar diferentes
pasos que hay que seguir al pie de la letra para que podamos de alguna manera lanzar cloud code y
luego enlazarlo directamente con Trading View. Para ello, volvemos a la terminal y escribimos cloud.
En este caso salen diferentes configuraciones, como puedes ver, en las cuales pues no hago nada, le
doy a enter, luego vuelvo a darle a enter y entonces permitimos que la terminal acceda a archivos.
Autorizamos. Y ahora pues al arrastrar desde la otra pantalla que yo tengo la terminal a la pantalla
que estáis viendo, ya podemos hablar directamente con Cloud Code, con acceso a nuestro propio
ordenador. Le damos a enter, nos van a salir varias preguntas, así que aceptamos las
configuraciones, entero. Aquí, bueno, pues vamos permitiendo o denegando cada uno lo que considere
el acceso a diferentes elementos. Y ya lo único que tenemos que hacer es pegar este prompt para que
Cloud instale el servidor MCP y lo agregue a la configuración para conectar definitivamente Trading
View. vamos a tener que ir aceptando diferentes parámetros y ejecutando pues otros comandos que
requieren de diferentes autorizaciones hasta que finalmente se nos termina abriendo automáticamente
la aplicación de escritorio de Trading View. Por eso era importante. Ejecutamos, aquí lo estamos
viendo, comandos finales y ya fíjate como la propia terminal nos indica que Trading View se ha
conectado correctamente. Con este paso dos, lo que hemos hecho, como comentaba, es lanzar Cloud Code
que habíamos instalado en el paso uno y pues a través de esa terminal de Cloud Code hablar con Cloud
Code directamente. más o menos lo mismo que si lo tuviéramos en el navegador, pero en este caso lo
teníamos en nuestra aplicación de escritorio y a través de la aplicación de escritorio hemos ido
ejecutando comandos hasta terminar conectando Cloud Code con Trading View. Ahora en el paso tres
explicaría cómo conectar Cloud Code con Trading View, pero es algo que ya hemos hecho. Así que lo
que voy a hacer es enseñarte de qué manera puedes h determinar si realmente se ha conectado
correctamente o no. Y para ello le vamos a pedir algo muy sencillo, como por ejemplo pedirle que
abra el gráfico de Apple con el ticker AA en nuestro Trading View. En la parte izquierda tenemos el
terminal de Cloud Code. Simplemente lo he hecho con pantalla grande y en la parte derecha nos
podemos fijar como no solo está Trading View, sino que también abre directamente el gráfico de
Apple. A partir de aquí podemos hacer literalmente lo que queramos. Yo pues justamente se me ha
abierto la parte de Trading View que tenía yo abierta, que es lo que he hecho durante la mañana,
lista de seguimiento y oportunidades de trading. Pero vamos a buscar algo muchísimo más sencillo,
por ejemplo, esta parte de aquí. Esto lo vamos a quitar y quedándonos con el gráfico de Bitcoin en
gráfico en temporalidad diaria le podemos pedir diferentes cosas. Por ejemplo, le voy a decir añade
el indicador RSI al gráfico diario. Le damos a enter y pues bueno, va a estar pensando, va a estar
maquinando, le vamos a dar a que sí y automáticamente se añade el indicador RSI. Otra cosa que le
podemos decir, qué sé yo, pon una alerta para que me avise cuando el precio de Bitcoin llegue a los
$80,000. Entonces, automáticamente le vamos a tener que aceptar la indicación. Esto de aceptar
constantemente se puede ajustar en la entrada, eh, o sea, se puede ajustar anteriormente en otra en
otro apartado de de cloud code en la propia terminal, pero bueno, yo en este caso no lo he hecho y
lo que ocurre es que constantemente pues me está haciendo preguntas sobre lo que me está pidiendo
que confirme lo que yo le estoy indicando, ¿no? Pero como digo, se puede eliminar completamente.
Aquí vemos cómo nos sale el apartado, le damos a crear y ahí vemos cómo termina creándose. Ha
tardado bastante en este caso porque ha estado verificando diferentes elementos de Trading Viiew, de
las APIs, del propio escritorio y demás, pero ya tenemos la alerta. Otra cosa un poquito más
compleja que le podemos pedir, pues por ejemplo, que nos analice un gráfico. Fijaros lo que le pongo
aquí. Analiza el gráfico diario según los indicadores y la sucesión de precios y dime qué está
pasando con Bitcoin en esta temporalidad. Así que lo que va a hacer automáticamente es meterse de
lleno en este gráfico, en lo que está ocurriendo, en los precios, en los indicadores que hay, que
ahora mismo hay dos medias móviles y un RSI, y determinar, hacer un análisis general en base a los
parámetros que yo le he comentado de lo que está haciendo Bitcoin. Ahí nos está ahora trasladando la
estructura de las últimas 100 velas y vamos a esperar a que lo desarrolle todo para pues entender un
poco cuál es el análisis que en este caso hace cloud en base a los elementos que yo le he indicado.
Ahí podemos ver que de alguna manera lo ha desarrollado en cuatro fases distintas, teniendo en
cuenta el precio del último mes, pues fase uno, pánico y lateralización del 22 de marzo al 5 de
abril. que es un poco todo esto que estamos viendo en esta parte final, el pánico y la
lateralización. Luego tenemos una fase número dos, impulso alcista, que es todo este recorrido de
aquí, una fase número tres, que es el pullback en el cual nos encontramos y una fase número cuatro
que es el rebote en soporte. Esto es en lo que hace referencia a el gráfico. Luego añade una lectura
implícita del RSI y finalmente una conclusión. Bitcoin está en un rebote técnico dentro de una
tendencia bajista mayor. También se ha podido apoyar en la media móvil de 200 sesiones diaria. Desde
el mínimo de 59,900 se ha recuperado un 27%, pero el precio sigue preso entre dos medias móviles
bajistas que actúan como techo. Es algo que es más que realista. El escenario más probable en el
corto plazo es compresión entre los 73,800 y 78,384. mientras el mercado decide si tiene fuerza para
atacar la media móvil roja o cualquier otro nivel, ¿no? Entonces, yo imaginaros que quiero ejecutar
una posición y digo, "Vale, mi estrategia me dice lo que sea." Por ejemplo, que yo lanzo niveles de
Fibonacci desde esta zona de aquí. Vamos a ponerlo que se vean un poquito mejor. Y yo lo que quiero
hacer es ejecutar una orden de compra en el nivel de 0,5, poniendo un stop loss en el nivel de 0,75
porque es lo que me indica mi estrategia y un take profit en esta zona de aquí. Entonces ahora, ¿qué
le puedo decir? Según tu análisis y según los parámetros de entrada, stop loss y take profit que he
marcado en el gráfico, consideras que es una buena ejecución. Es decir, estoy diciendo que mezcle el
análisis que Cloud me ha determinado, media móvil, RSI, los precios, la lateralización, el impulso
tal, con las bases de mi estrategia de trading, por ejemplo, y que en base a lo que mi estrategia de
trading me indica que yo debería hacer como punto de entradas y puntos de salida, oye, esto está
bien o esto está mal, Pues vamos a ver qué es lo que comenta Cloud. Y aquí tenemos un poco las
conclusiones en las cuales está primero evaluando el setup, luego evaluando lo que ve en el gráfico
y luego tratando los diferentes puntos, ¿no? Rentabilidad, riesgo, lo cual determina qué es el
problema principal. Habla también de lo que juega a favor, de lo que juega en contra y finalmente
dictamina una conclusión final. No es una estrategia óptima como tal lo que está planteado. La idea
estructural tiene sentido, rebote y continuación, pero el rentabilidad riesgo no compensa el riesgo
a operar en contra de la tendencia. Y luego, fijaros que lo que hace es literalmente determinar dos
opciones distintas que ayudarían de alguna forma a mejorar esta estrategia o esta estructura. Para
finalizar, yendo de menos a más complejo, aunque como digo, se pueden hacer más cosas, ¿por qué no
creamos un indicador? Fíjate, yo le voy a dar a unos parámetros, que en este caso es un texto de 11
líneas para que me cree un indicador, un indicador que yo me he inventado, que se llama, por
ejemplo, Macrotop Hunter. Evidentemente le he pedido a Cloud que me diga un nombre atractivo para
este indicador y es un indicador que se basa en buscar momentos donde el precio sigue subiendo, pero
el impulso ya se está agotando, detectando esto por una divergencia bajista entre el precio y el
MACD. Al mismo tiempo, el indicador exige que el precio esté muy alejado de sus medias móviles. He
puesto una de 21 y una de 50 periodos, lo que indica una especie de sobreextensión, ¿no? Y
finalmente, la tercera y última condición es que la volatilidad esté comprimida en zona de máximos,
algo que suele anticipar de alguna forma movimientos a la baja, ya sea en forma de corrección o lo
que sea. Finalmente, el RSI en temporalidad diaria, ya que estamos en gráfico diario, tiene que
estar en sobrecompra validando que el agotamiento no es algo local, sino que también el marco un
poco grande, el marco temporal mayor está indicando la misma estructura. Y luego, pues bueno, ya
para hacer la gracia, le he pedido que me indique en la parte superior derecha de cada condición un
símbolo u otro en tiempo real para evaluar la calidad y que también pues que me explique o me ponga
con una especie de calavera, ya que va un poco con el rollo del indicador macrotop Hunter cuando se
están dando las condiciones. Así que vamos a esperar y vamos a ver qué es lo que hace Cloud Code con
este prompt que le he pasado. Aquí vemos como sale en Pinecript. Al final pues es la parte esta de
Trading View en la cual se pueden hacer back testings, puedes crear indicadores, estrategias, puedes
hacer absolutamente lo que quieras. Por eso, pues también se pueden crear tus propias estrategias de
trading a través de de este de cloud code. Y nada, pues lo bueno de esto es que en el momento o en
los momentos en los cuales esté detectando el propio Pine script que hay algún tipo de problema,
algún tipo de error que puede ocurrir y muchas veces y más cuando creas desde cero un indicador tan
random como el que acabo de crear, pues automáticamente se conecta, como ya está conectado a Cloud
Code y se arregla solo. Normalmente si tú no tienes Cloud Code y Trading View conectados, como hemos
visto en otros vídeos donde he creado estrategias de trading desde cero donde hemos generado
ganancias de 500 y 700% en cuestión de años, pero así ha sido, hemos tenido que detectar errores,
copiar el error, pasarlo e ir solventándolo. En este caso, no. En este caso se hace todo de manera
totalmente automática, ya que Cloud Code está correlacionado y enlazado al 100% con Trading View.
Entonces, bueno, voy a quitarle un poco de espacio a esto para que se vea mejor el propio indicador.
Estos son dibujos que automáticamente está poniendo del propio indicador, pero bueno, vamos a ver
cómo termina de de enlazarse. Y aquí vemos como ya nos ha determinado y nos ha añadido el indicador
al gráfico Macrotop Hunter. Fijaros que pues ha tenido que añadir la media móvil extra, etcétera,
etcétera. Indica aquí los parámetros que hemos mencionado. La media móvil naranja es la de 21
sesiones, la de eh la otra es la de 50, esta de aquí. Y nada, tenemos el resumen del indicador en
marcha. Podríamos pedirle desde aquí un montón de cosas, como por ejemplo que nos indicara los
momentos anteriores de mercado en los cuales se ha dado la señal de compra o de venta, etcétera,
etcétera. Pero lo que tenemos aquí es en la parte superior derecha un grupo de señales para ver si
realmente se están dando las condiciones de ejecución. RSI que no se da el ATR comprimido, el precio
estirado por las SEMAS, divergencia más dibajista, es decir, ahora mismo no hay ninguna señal. En el
momento en el cual se fueran dando todas y cada una de las señales, pues se irían poniendo de color
verde. Pero lo mejor de esto es que pues es simplemente un conjunto de tareas básicas, fáciles,
simples y sencillas, que yo le he pedido a Cloud Code, pero a partir de aquí se pueden hacer miles
de tareas mucho más complejas. Dicho esto, recuerda que abajo en el primer comentario fijado y la
descripción del vídeo encontrarás el enlace a mi Telegram oficial y en el cual podrás a través de la
búsqueda descargarte totalmente gratis un PDF en el cual explico paso a paso todas y cada una de las
indicaciones que hemos seguido con proms y comentarios a tener en cuenta. Además, también
encontrarás otros enlaces de interés sobre cloud, sobre trading, sobre cloud y trading, todo
contenido 100% gratuito para que sigas formándote sin necesidad de invertir tu dinero. Este vídeo lo
voy a dejar por aquí. Espero que te haya gustado, que te haya servido, que es lo importante. Si es
así, dale me gusta, suscríbete, compártelo con amigos, con la familia y nos vemos en el próximo
vídeo. Dios.
