create table users (
       id serial primary key,
       username varchar(20) not null,
       pwdhash bytea not null,
       email varchar(28) not null,
       role integer not null
);

create table servers (
       id serial primary key,
       name varchar(200) not null,
       title varchar(200) not null,
       url varchar(1024) not null,
       capabilites text,
       login varchar(20),
       passwd varchar(128),
       owner_id integer not null references users(id),
       pub boolean not null
);

create table layers (
       id serial primary key,
       server_id integer references servers(id),
       name varchar(128) not null,
       title varchar(128) not null,
       abstract text,
       keywords text,
       latlngbb text,
       capabilites text,
       pub boolean not null,
       parent_id integer references layers(id),
       available boolean not null default true
);

create unique index layers_server_id_name_uniq on layers(server_id, name);

create table layerset (
       id serial primary key,
       name varchar(32) not null,
       title varchar(128) not null,
       abstract text,
       author_id integer not null references users(id),
       pub boolean not null
);

create unique index layer_name_uniq on layerset (name);

create table layertree (
       id serial primary key,
       name varchar(32),
       layer_id integer references layers(id),
       parent_id integer references layertree(id),
       lset_id integer references layerset(id),
       ord integer not null,
       hidden boolean not null
);

CREATE UNIQUE INDEX layertree_order_uniq ON layertree (parent_id, lset_id, ord);

CREATE UNIQUE INDEX layertree_name_uniq  ON layertree (name, lset_id);
