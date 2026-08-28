CREATE TABLE `trial_signups` (
	`id` int AUTO_INCREMENT NOT NULL,
	`email` varchar(320) NOT NULL,
	`source` varchar(64) NOT NULL DEFAULT 'landing_hero',
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `trial_signups_id` PRIMARY KEY(`id`),
	CONSTRAINT `trial_signups_email_unique` UNIQUE(`email`)
);
