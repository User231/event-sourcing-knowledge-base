# What is Event Sourcing?

Source: https://www.eventstore.com/blog/what-is-event-sourcing

# What is Event Sourcing?

Alexey Zimarev

•Fri Jun 30 2023

[Foundational](/blog/category/foundational) [Event Sourcing](/blog/category/event-sourcing) [Domain Event](/blog/category/domain-event) [Event Store](/blog/category/event-store) [Event Stream](/blog/category/event-stream) [Command](/blog/category/command) [Cqrs](/blog/category/cqrs) [Projection](/blog/category/projection) [Dotnet](/blog/category/dotnet) [Csharp](/blog/category/csharp) [Sample](/blog/category/sample)

Event Sourcing is an alternative way to persist data. In contrast with state-oriented persistence that only keeps the latest version of the entity state, Event Sourcing stores each state mutation as a separate record called an event.

> Model information about activity in the domain as a series of discrete events. Represent each event as domain object.
>
> Eric Evans, Domain-Driven Design Reference

Further in this section, weâll stick to the definition of Event Sourcing as Greg Young formulated it back in 2007, based on concepts from Domain-Driven Design. Therefore, in this section, we will use the terms âdomain eventâ and âeventâ interchangeably.

## State-oriented persistence

All real-life systems store data. There is a vast number of different types of data storage, but usually, developers use databases to keep the data safe. Computerised databases appeared right after computers started to enter the business landscape.

Hierarchical databases were quickly outlived by relational databases that started their ascendance in the 1970s when the first query languages called QUEL and SEQUEL appeared. Since the 1980s, when SQL became the standard query languages for relational databases and various RDBMSes like Oracle, IBM DB/2, and Microsoft SQL Server started to dominate the world of data persistence.

However, with the rise of object-oriented programming, which became mainstream in the late 1990s, developers started to struggle to persist objects in relational databases. Such a struggle got the name âobject-relational impedance mismatchâ. Alternative families of databases appeared over the decades to address the mismatch issues, starting from older object databases to more modern document databases.

Albeit, no matter what database kind the application uses, all that is stored in the database is the current state of the system. Essentially, all DMBSes support four basic operations for persistence - create, read, update and delete (CRUD).

System objects usually are persisted as database records - rows in tables or documents. It means that when the object changes, and the change needs to be persisted, the database record gets replaced by a new record, which contains updated values.

Order presumably paid

## Historical record

### Keeping the history

Often keeping only the current state of an entity is not enough. For example, for orders, weâd probably want to keep the history of status changes. When such a requirement is present, developers often choose to save a particular update history in a separate table or document collection. Such a history, however, only tackles a specific use case and needs to be built upfront.

Order history is lost

Even when such a solution gets implemented and deployed, there is no guarantee that tomorrow or next year, the business wonât require keeping the record on other state changes. Again, all the history before the change that would keep such a record will be lost. Another issue with only keeping the current entity state is that all the changes that happen in the database are, by nature, implicit.

> Change history of entities can allow access to previous states, but ignores the meaning of those changes, so that any manipulation of the information is procedural, and often pushed out of the domain layer.
>
> Eric Evans, Domain-Driven Design Reference

Any change of a persisted entity is just another update, indistinguishable from all other updates. When we look, for example, at the `Order` entity and its `Status` property, if it gets updated to `Paid` or `Shipped` we could figure out (implicitly) what has happened. However, if the `Total` property value changes, how would we possibly know what triggered that change?

### Explicit mutations as events

When using domain events, which, in turn, use domain terminology (Ubiquitous Language) to describe state changes, we have an explicit description of the change.

Order paid as an event

The payment case might be a bit too simple to disclose the difference, so, letâs use another example. Imagine that the total order amount changes for a different reason. Here is how the change would be done if we only keep the entity state:

Order Total changed

Here an implicit update has been applied to the entity state, and the only way for us to know what happened is to look at some sort of audit trail or even the application log.

When we model state changes as domain events, we can make those changes explicit and use the domain language to describe the change. Below you can see that two completely different operations couldâve happened that lead to exactly the same outcome if we only look at the final state.

Total changes because of discount

When a discount is applied to the order, the total amount changes.

Total changes because an item was removed

Again, the total amount could also change for other reasons, like removing an order item.

### Domain event in code

So, how would a domain event look when implemented in code? It is a simple property bag. We have to ensure that we can serialise it for persistence, and, also, can deserialize it back when the time comes to read the event from the database.

```
public class DiscountAppliedToOrder {
    public string OrderId { get; set; }
    public double DiscountAmount { get; set; }
    public double NewTotalAmount { get; set; }
}
```

> A domain event is a fully-fledged part of the domain model, a representation of something that happened in the domain.
>
> Eric Evans, Domain-Driven Design Reference

## Entities as event streams

So, Event Sourcing is the persistence mechanism where each state transition for a given entity is represented as a domain event that gets persisted to an event database (event store). When the entity state mutates, a new event is produced and saved. When we need to restore the entity state, we read all the events for that entity and apply each event to change the state, reaching the correct final state of the entity when all available events are read and applied.

## Command handling flow

Since we already used the order example in this section, we can compose an entity that represents an order:

```
public class Order {
    OrderId id;
    OrderItem[] items;
    Money totalAmount;

    public AddItem(OrderItem newItem) {
        if (!CanAddItem(item))
            throw new DomainException("Unable to add the item");

        items.Add(newItem);
        totalAmount = totalAmount.Add(newItem.LineTotal);
    }
}
```

In this example, we use the Domain Model pattern, so the entity has both state and behaviour. State transitions occur when we call entity methods, so the flow of execution for any operation would look like this:

State-oriented flow

If our application uses a Ports and Adapters architecture, we would have an application service, which handles the command:

```
public class OrderService {
    EntityStore store;

    public Response Handle(AddOrderItem command) {
        var order = store.Load<Order>(command.OrderId);
        var orderItem = OrderItem.FromCommand(command.Item);
        order.AddItem(orderItem);
        store.Save(order);
    }
}
```

Weâd also have an edge adapter, like HTTP that accepts commands from the outside world, but itâs out of scope for this article.

## Event-based entity

Now, letâs see what needs to change for our application to use Event Sourcing.

### Event as code

First, we need an event that represents the state transition:

```
public class ItemAdded {
    public string OrderId;
    public Shared.OrderItem Item;
    public double Total;
}
```

NOTE

Notice that event properties are primitive types or shared complex types, which All the types used for events, including shared types, are just property bags (DTOs) and should not contain any logic. The main attribute of these types is that they must be serializable.

The event now describes the domain-specific behaviour and contains enough information to mutate the `Order` entity state.

### Producing events

Second, we need to change the entity code, so it will generate an event:

```
public class Order {
    OrderId id;
    OrderItem[] items;
    Money totalAmount;

    public AddItem(OrderItem newItem) {
        if (!CanAddItem(item))
            throw new DomainException("Unable to add the item");

        var newTotal = totalAmount.Add(newItem.LineTotal).AsDouble;
        Apply(
            new ItemAdded {
                OrderId = id,
                Item = Map(newItem),
                Total = newTotal
            }
        );
    }
}
```

At this stage, the `AddItem` method doesnât directly mutate the entity state, but produces an event instead. It uses the `Apply` method, which doesnât exist in the `Order` class yet, so we need to implement it.

### Collect changes

Every new event is a change. The `Order` class should keep track of all the changes that happen during the command execution flow, so we can persist those changes in the command handler. Such a behaviour is generic and not unique to the `Order` class, so we can make an abstract class to isolate the technical work in it:

```
public abstract class Entity {
    List<object> changes;

    public void Apply(object event) {
        changes.Add(event);
    }
}
```

We can now change the `Order` class to inherit from the `Entity` class, and the code will compile. However, notice that the entity state doesnât change when we produce a new event. It might be not a problem if we only produce one event when handling a command, but thatâs not always the case. For example, when adding a new item we could produce two events: `ItemAdded` and `TotalUpdated` to make state changes more explicit and atomic. In some cases, the code that produces consequent events, but still being in the same transaction, need to know the new entity state, changed by the previous event. Therefore, we need to mutate the state in-process when we apply each event.

### Using events to mutate state

Letâs first implement the method that mutates the entity state using events. Itâs common to call this method `When`. We can add an abstract method to the base class and ensure itâs called when we add new events to the list of changes:

```
public abstract class Entity {
    List<object> changes;

    public void Apply(object event) {
        When(event);
        changes.Add(event);
    }

    protected abstract void When(object event);
}
```

Now, we can implement the `When` method in the `Order` class:

```
public class Order {
    OrderId id;
    OrderItem[] items;
    Money totalAmount;

    public AddItem(OrderItem newItem) {
        if (!CanAddItem(item))
            throw new DomainException("Unable to add the item");

        var newTotal = totalAmount.Add(newItem.LineTotal).AsDouble;
        Apply(
            new ItemAdded {
                OrderId = id,
                Item = Map(newItem),
                Total = newTotal
            }
        );
    }

    protected void When(object event) {
        switch (event) {
            case ItemAdded e:
                items.Add(OrderItem.FromEvent(e.Item));
                totalAmount = e.Total;
                break;
        }
    }
}
```

Essentially, in order to restore the entity state from events, we need to apply the left [fold](https://en.wikipedia.org/wiki/Fold_(higher-order_function)) on all the events in the entity stream.

With all these changes, the `Order` class public API hasnât changed. It still exposes the `AddItem` method and only the internal implementation is different.

## Using events for persistence

Now, letâs get back to the original command handling flow and see how it changed since we started using events.

In fact, the overall flow is the same, so is the application service code. The only change is how the `EntityStore` adapter works. For state-oriented persistence, it is something like putting the entity state to a document, serialising it and storing it in a document database, and then reading it back. How would it look when we have an event-sourced entity? We use the same port, so the API doesnât change. We need to implement an adapter that can use an event-oriented database, like Event Store.

In terms of persisting objects, the main use case for an event database is to be able to store and load events for a single object or entity, using the entity identifier. The main difference is that when you use a relational or document database and use the entity id to get the data, you get a single record, which directly represents the current entity state. In contrast, when you retrieve an entity from an event database, you get multiple records for one id and each record in the set is an event.

Therefore, the whole set of events that represents a single entity has one unique identifier. Since we donât have a single record, which is assigned to that identifier, we call that event set a *stream*. The stream is an ordered collection of events for a single object in the system. The object identifier combined with the object type is often used as the stream name.

Entity as a stream of events

When we read all events from a single entity stream, we can reconstruct the current state by calling the `When` method for all the events, in sequence.

With an abstract event-oriented database, the `EntityStore` adapter would look similar to the code below:

```
public class EntityStore {
    EventDatabase db;
    Serializer serializer;

    public void Save<T>(T entity) where T : Entity {
        var changes = entity.changes;
        if (changes.IsEmpty()) return; // nothing to do

        var dbEvents = new List<DbEvent>();
        foreach (var event in changes) {
            var serializedEvent = serializer.Serialize(event);
            dbEvents.Add(
                data: new DbEvent(serializedEvent),
                type: entity.GetTypeName();
            );
        }
        var streamName = EntityStreamName.For(entity);
        db.AppendEvents(streamName, dbEvents);
    }

    public T Load<T>(string id) where T : Entity {
        var streamName = EntityStreamName.For(entity);
        var dbEvents = db.ReadEvents(streamName);
        if (dbEvents.IsEmpty()) return default(T); // no events

        var entity = new T();
        foreach (var event in dbEvents) {
            entity.When(event);
        }
        return entity;
    }
}
```

One important thing to mention here is that the code that mutates the entity state based on the information stored in events, should not have any advanced logic or calculations. Preferably, the event already contains all the required information, so the `When` method can use it directly to change entity state properties. By following this pattern, you will ensure that state transitions are stable, and the current entity state will always be predictable.

[Back to all posts](/blog)