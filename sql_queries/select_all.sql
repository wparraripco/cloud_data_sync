SELECT top(10) * from lookup.users;

SELECT top(10) * from core.test_contacts;

SELECT top(10) * from core.test_properties;

SELECT top(10) * from bridge.properties_contacts;

SELECT top(10) * from bridge.users_contacts;

SELECT top(10) * from bridge.users_properties;


-- USE [Ripco_Monday_Data];
-- GO

-- DROP TABLE IF EXISTS bridge.monday_board1_people;
-- DROP TABLE IF EXISTS bridge.monday_board2_people;
-- DROP TABLE IF EXISTS bridge.monday_board1_board2_relations;
-- DROP TABLE IF EXISTS entity.monday_board1_items;
-- DROP TABLE IF EXISTS entity.monday_board2_items;
-- DROP TABLE IF EXISTS lookup.monday_users;
-- GO

-- USE [Ripco_Monday_Data];
-- GO

-- CREATE SCHEMA core;
-- GO

-- -- 1. lookup.users
-- CREATE TABLE lookup.users (
--     user_id         BIGINT          NOT NULL,
--     name            NVARCHAR(255)   NOT NULL,
--     email           NVARCHAR(255)   NULL,
--     title           NVARCHAR(255)   NULL,
--     is_enabled      BIT             NOT NULL DEFAULT 1,
--     is_admin        BIT             NOT NULL DEFAULT 0,
--     is_guest        BIT             NOT NULL DEFAULT 0,
--     photo_thumb_url NVARCHAR(500)   NULL,
--     synced_at       DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
--     CONSTRAINT PK_users PRIMARY KEY (user_id)
-- );
-- GO

-- -- 2. core.test_properties  (Board 1 — 18415335792)
-- CREATE TABLE core.test_properties (
--     item_id             BIGINT          NOT NULL,
--     group_id            NVARCHAR(100)   NOT NULL,
--     group_name          NVARCHAR(255)   NULL,
--     name                NVARCHAR(500)   NOT NULL,
--     location_address    NVARCHAR(500)   NULL,
--     location_city       NVARCHAR(255)   NULL,
--     location_country    NVARCHAR(100)   NULL,
--     location_lat        DECIMAL(10,7)   NULL,
--     location_lng        DECIMAL(10,7)   NULL,
--     location_place_id   NVARCHAR(255)   NULL,
--     status              NVARCHAR(100)   NULL,
--     date                DATE            NULL,
--     created_at          DATETIME2       NULL,
--     updated_at          DATETIME2       NULL,
--     synced_at           DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
--     CONSTRAINT PK_test_properties PRIMARY KEY (item_id)
-- );
-- GO

-- -- 3. core.test_contacts  (Board 2 — 18415335878)
-- CREATE TABLE core.test_contacts (
--     item_id         BIGINT          NOT NULL,
--     group_id        NVARCHAR(100)   NOT NULL,
--     group_name      NVARCHAR(255)   NULL,
--     name            NVARCHAR(500)   NOT NULL,
--     date            DATE            NULL,
--     email           NVARCHAR(255)   NULL,
--     email_label     NVARCHAR(255)   NULL,
--     created_at      DATETIME2       NULL,
--     updated_at      DATETIME2       NULL,
--     synced_at       DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
--     CONSTRAINT PK_test_contacts PRIMARY KEY (item_id)
-- );
-- GO

-- -- 4. bridge.properties_contacts
-- CREATE TABLE bridge.properties_contacts (
--     id                  INT     NOT NULL IDENTITY(1,1),
--     property_item_id    BIGINT  NOT NULL,
--     contact_item_id     BIGINT  NOT NULL,
--     CONSTRAINT PK_properties_contacts  PRIMARY KEY (id),
--     CONSTRAINT UQ_properties_contacts  UNIQUE (property_item_id, contact_item_id),
--     CONSTRAINT FK_pc_property FOREIGN KEY (property_item_id) REFERENCES core.test_properties (item_id),
--     CONSTRAINT FK_pc_contact  FOREIGN KEY (contact_item_id)  REFERENCES core.test_contacts   (item_id)
-- );
-- GO
-- CREATE INDEX IX_pc_contact_item_id ON bridge.properties_contacts (contact_item_id);
-- GO

-- -- 5. bridge.users_properties
-- CREATE TABLE bridge.users_properties (
--     id          INT     NOT NULL IDENTITY(1,1),
--     item_id     BIGINT  NOT NULL,
--     user_id     BIGINT  NOT NULL,
--     CONSTRAINT PK_users_properties  PRIMARY KEY (id),
--     CONSTRAINT UQ_users_properties  UNIQUE (item_id, user_id),
--     CONSTRAINT FK_up_item FOREIGN KEY (item_id)  REFERENCES core.test_properties (item_id),
--     CONSTRAINT FK_up_user FOREIGN KEY (user_id)  REFERENCES lookup.users         (user_id)
-- );
-- GO
-- CREATE INDEX IX_users_properties_user_id ON bridge.users_properties (user_id);
-- GO

-- -- 6. bridge.users_contacts
-- CREATE TABLE bridge.users_contacts (
--     id          INT     NOT NULL IDENTITY(1,1),
--     item_id     BIGINT  NOT NULL,
--     user_id     BIGINT  NOT NULL,
--     CONSTRAINT PK_users_contacts  PRIMARY KEY (id),
--     CONSTRAINT UQ_users_contacts  UNIQUE (item_id, user_id),
--     CONSTRAINT FK_uc_item FOREIGN KEY (item_id)  REFERENCES core.test_contacts (item_id),
--     CONSTRAINT FK_uc_user FOREIGN KEY (user_id)  REFERENCES lookup.users       (user_id)
-- );
-- GO
-- CREATE INDEX IX_users_contacts_user_id ON bridge.users_contacts (user_id);
-- GO
