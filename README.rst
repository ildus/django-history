Общее описание
--------------

Приложение для сохранения истории изменений
объектов. Технику взял из книги [Pro Django (автор Marty Alchin)][1].

Приложение умеет:

  1. сохранять все изменения объекта 
  2. откатывать изменения 
  3. просто включается, не требует создания вручную моделей для сохранения истории, при этом история изменений хранится в разных таблицах для каждой модели 

Можно установить с помощью pip:

    pip install -e git+git://github.com/ildus/django-history.git#egg=django-history

Установка:
----------

  * добавляем в мидлвары `django_history.current_context.CurrentUserMiddleware`
  * в модели, для которого нужно сохранять историю, добавляем   
  
    
    from django_history.models import HistoricalRecords
    history = HistoricalRecords()

  * выполнить syncdb 

  
Middleware нужен, для того чтобы сохранить какой пользователь сделал
изменения.

Использование:
--------------

Можно получить историю всех изменений в модели или объекте модели. Например,
так

    >>> from main.models import Poll
    >>> Poll.objects.create(language = 'en',question = 'Where are we?')
    <Poll: Where are we?>
    >>> poll = Poll.objects.all()[0]
    >>> poll.language = 'ru'
    >>> poll.save()
    >>> poll.history.all()
    [<HistoricalPoll: Changed by None on 2011-09-10 15:49:48.609916, {'language': (u'en', 'ru')}>, <HistoricalPoll: Created by None on 2011-09-10 15:49:00.355074, {}>]
    
При авторизованном пользователе, будет видно кто изменил объект.

Можно откатывать изменения. Нужно учесть, что откат тоже является изменением и
тоже идет в историю

    >>> poll.history.all()[0].revert()
    >>> poll.history.all()
    [<HistoricalPoll: Changed by None on 2011-09-10 17:24:30.570957, {'language': (u'ru', u'en')}>, <HistoricalPoll: Created by None on 2011-09-10 15:49:00.355074, {}>]
    
Можно получать историю не только по объекту, но и по всей модели

    >>> poll2 = Poll.objects.create(language = 'cz',question = 'Who are we?')
    >>> poll2.language = 'cs'
    >>> poll2.save()
    >>> Poll.history.all()
    [<HistoricalPoll: Changed by None on 2011-09-10 17:27:01.669054, {'language': (u'cz', 'cs')}>, <HistoricalPoll: Created by None on 2011-09-10 17:26:30.827953, {}>, <HistoricalPoll: Created by None on 2011-09-10 17:25:57.839304, {}>, <HistoricalPoll: Changed by None on 2011-09-10 17:24:30.570957, {'language': (u'ru', u'en')}>, <HistoricalPoll: Created by None on 2011-09-10 15:49:00.355074, {}>]
    
Вот и все! Детали реализации лучше смотреть прямо в коде, благо его там не так
много. А если коротко, то все реализовано через сигналы и метода
contribute_to_class, который отрабатывает для полей модели.

   [1]: http://prodjango.com/

